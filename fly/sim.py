"""Leaky-integrate-and-fire reservoir simulator over a connectome graph.

Follows the LIF + exponential-current-synapse formulation used in
Shiu et al. 2024 (Nature), "A leaky integrate-and-fire computational
model based on the connectome of the entire adult *Drosophila* brain
reveals insights into sensorimotor processing." Their synaptic
weights (0.275 mV per synapse) are assumed to already be baked into
``W`` (the graph is a weighted sum of synapse counts * per-synapse
mV, sign-adjusted for excitatory/inhibitory neurotransmitter).

Units: mV for voltages/currents, ms for time.

State update per step (exponential Euler, no synaptic delays beyond
the implicit one-step delay from using the *previous* step's spikes):

    i_syn <- i_syn * exp(-dt/tau_syn) + W @ spikes_prev
    v     <- v + (dt/tau_mem) * (v_rest - v + i_syn + i_ext)   [if not refractory]
    v     <- v_reset                                          [if refractory]
    refrac_left <- max(refrac_left - dt, 0)
    spiked = (not refractory) & (v >= v_thresh)
    v[spiked] = v_reset ; refrac_left[spiked] = refrac
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np
import scipy.sparse as sp


def _concat_csc_ranges(indptr: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Vectorized equivalent of ``np.concatenate([range(s,e) for s,e in ...])``.

    Given CSC ``indptr`` and a set of column indices ``idx``, return the
    flat array of positions into ``indices``/``data`` covering all of
    those columns' slices, without a Python-level loop over ``idx``.
    """
    starts = indptr[idx]
    ends = indptr[idx + 1]
    counts = ends - starts
    total = int(counts.sum())
    if total == 0:
        return np.empty(0, dtype=np.int64)
    # Position of each element within its own column's run, then offset
    # by that column's start in the underlying indices/data arrays.
    run_starts = np.repeat(np.cumsum(counts) - counts, counts)
    within = np.arange(total, dtype=np.int64) - run_starts
    return np.repeat(starts, counts) + within


class Reservoir:
    """LIF spiking reservoir driven by a fixed weighted connectome graph.

    Parameters
    ----------
    W_csr : scipy.sparse.csr_matrix
        W[post, pre] in mV (synapse-count-weighted, sign already applied
        for excitatory/inhibitory neurotransmitter).
    spmv_method : {"auto", "dense", "gather"}
        How to compute ``W @ spikes_prev`` each step:
          - "dense": build a dense 0/1 float32 spike vector and do a
            standard CSR sparse-matvec (``W @ s``). Cost is O(nnz)
            every step regardless of how many neurons spiked.
          - "gather": store W as CSC too, and for each spiking
            presynaptic neuron slice out its column (post-synaptic
            targets + weights) directly, then scatter-add with
            ``np.bincount``. Cost is O(sum of out-degrees of neurons
            that actually spiked this step) -- much cheaper than
            "dense" when the population is sparsely active (the
            typical regime for a biologically-tuned reservoir at
            single-digit-to-low-double-digit Hz).
          - "auto" (default): benchmark both on a synthetic spike
            pattern at ``calib_spike_frac`` activity and keep the
            faster one for the lifetime of this Reservoir.
    """

    def __init__(
        self,
        W_csr: sp.csr_matrix,
        dt: float = 1.0,
        tau_mem: float = 20.0,
        tau_syn: float = 5.0,
        v_rest: float = -52.0,
        v_reset: float = -52.0,
        v_thresh: float = -45.0,
        refrac: float = 2.2,
        i_drive: Optional[np.ndarray] = None,
        spmv_method: str = "auto",
        calib_spike_frac: float = 0.03,
        seed: int = 0,
    ):
        if not sp.isspmatrix_csr(W_csr):
            W_csr = sp.csr_matrix(W_csr)
        self.N = W_csr.shape[0]
        assert W_csr.shape == (self.N, self.N), "W must be square [post, pre]"

        self.W_csr = W_csr.astype(np.float32)
        self.W_csc = self.W_csr.tocsc()
        # Raw arrays for the "gather" path (avoid scipy per-call overhead).
        self._csc_indptr = self.W_csc.indptr.astype(np.int64)
        self._csc_indices = self.W_csc.indices.astype(np.int64)
        self._csc_data = self.W_csc.data.astype(np.float32)

        self.dt = float(dt)
        self.tau_mem = float(tau_mem)
        self.tau_syn = float(tau_syn)
        self.v_rest = np.float32(v_rest)
        self.v_reset = np.float32(v_reset)
        self.v_thresh = np.float32(v_thresh)
        self.refrac = np.float32(refrac)
        # i_drive: optional constant baseline external input (mV), added
        # to whatever per-step i_ext the caller passes into run()/step().
        self.i_drive = (
            np.zeros(self.N, dtype=np.float32)
            if i_drive is None
            else np.asarray(i_drive, dtype=np.float32)
        )

        self.decay_syn = np.float32(np.exp(-self.dt / self.tau_syn))
        self.alpha = np.float32(self.dt / self.tau_mem)

        self.v = np.full(self.N, self.v_rest, dtype=np.float32)
        self.i_syn = np.zeros(self.N, dtype=np.float32)
        self.refrac_left = np.zeros(self.N, dtype=np.float32)
        self._spikes_prev = np.zeros(self.N, dtype=bool)

        self.spmv_timings_s: Optional[dict] = None
        self.spmv_method = self._select_spmv_method(spmv_method, calib_spike_frac, seed)

    # ------------------------------------------------------------------
    # spike-driven synaptic input: two interchangeable implementations
    # ------------------------------------------------------------------
    def _spmv_dense(self, idx: np.ndarray) -> np.ndarray:
        s = np.zeros(self.N, dtype=np.float32)
        s[idx] = 1.0
        return self.W_csr @ s

    def _spmv_gather(self, idx: np.ndarray) -> np.ndarray:
        if idx.size == 0:
            return np.zeros(self.N, dtype=np.float32)
        offsets = _concat_csc_ranges(self._csc_indptr, idx)
        if offsets.size == 0:
            return np.zeros(self.N, dtype=np.float32)
        post = self._csc_indices[offsets]
        w = self._csc_data[offsets]
        return np.bincount(post, weights=w, minlength=self.N).astype(np.float32)

    def _select_spmv_method(self, method: str, calib_frac: float, seed: int) -> str:
        if method in ("dense", "gather"):
            self._spmv_fn = self._spmv_dense if method == "dense" else self._spmv_gather
            return method
        if method != "auto":
            raise ValueError(f"unknown spmv_method: {method!r}")

        rng = np.random.default_rng(seed)
        n_active = max(1, min(self.N, int(round(calib_frac * self.N))))
        idx = np.sort(rng.choice(self.N, size=n_active, replace=False)).astype(np.int64)

        reps = 5
        # Warm up (first call may pay allocation / cache costs) then time.
        self._spmv_dense(idx)
        t0 = time.perf_counter()
        for _ in range(reps):
            self._spmv_dense(idx)
        t_dense = (time.perf_counter() - t0) / reps

        self._spmv_gather(idx)
        t0 = time.perf_counter()
        for _ in range(reps):
            self._spmv_gather(idx)
        t_gather = (time.perf_counter() - t0) / reps

        self.spmv_timings_s = {"dense": t_dense, "gather": t_gather}
        if t_gather <= t_dense:
            self._spmv_fn = self._spmv_gather
            return "gather"
        self._spmv_fn = self._spmv_dense
        return "dense"

    # ------------------------------------------------------------------
    # core dynamics
    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.v = np.full(self.N, self.v_rest, dtype=np.float32)
        self.i_syn = np.zeros(self.N, dtype=np.float32)
        self.refrac_left = np.zeros(self.N, dtype=np.float32)
        self._spikes_prev = np.zeros(self.N, dtype=bool)

    def step(self, i_ext: np.ndarray) -> np.ndarray:
        """Advance one dt. Returns bool[N] of neurons that spiked."""
        idx = np.flatnonzero(self._spikes_prev)
        self.i_syn = self.i_syn * self.decay_syn + self._spmv_fn(idx)

        refrac_mask = self.refrac_left > 0.0
        total_input = self.i_drive + np.asarray(i_ext, dtype=np.float32)
        dv = self.alpha * (self.v_rest - self.v + self.i_syn + total_input)
        v_new = self.v + dv
        self.v = np.where(refrac_mask, self.v_reset, v_new)

        self.refrac_left = np.maximum(self.refrac_left - self.dt, np.float32(0.0))

        spiked = (~refrac_mask) & (self.v >= self.v_thresh)
        self.v[spiked] = self.v_reset
        self.refrac_left[spiked] = self.refrac

        self._spikes_prev = spiked
        return spiked

    def run(
        self,
        i_ext: np.ndarray,
        n_steps: int,
        frame_every: int = 0,
        on_frame: Optional[Callable[[np.ndarray], None]] = None,
        count_idx: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Run ``n_steps`` and return per-neuron spike counts (int32).

        If ``count_idx`` is given, counts are restricted to (and ordered
        like) those indices. If ``frame_every > 0`` and ``on_frame`` is
        given, it is called every ``frame_every`` steps with the sorted
        uint32 indices of all neurons that spiked at least once since
        the previous call (frame accumulator is cleared after each call).
        """
        i_ext = np.asarray(i_ext, dtype=np.float32)
        if count_idx is None:
            counts = np.zeros(self.N, dtype=np.int32)
        else:
            count_idx = np.asarray(count_idx)
            counts = np.zeros(count_idx.shape[0], dtype=np.int32)

        frame_accum = None
        if frame_every and on_frame is not None:
            frame_accum = np.zeros(self.N, dtype=bool)

        for t in range(n_steps):
            spiked = self.step(i_ext)
            if count_idx is None:
                counts += spiked
            else:
                counts += spiked[count_idx]
            if frame_accum is not None:
                frame_accum |= spiked
                if (t + 1) % frame_every == 0:
                    on_frame(np.flatnonzero(frame_accum).astype(np.uint32))
                    frame_accum[:] = False

        return counts

    # ------------------------------------------------------------------
    # loading
    # ------------------------------------------------------------------
    @classmethod
    def from_npz(cls, path, **kwargs) -> "Reservoir":
        with np.load(path) as d:
            W = sp.csr_matrix(
                (d["data"], d["indices"], d["indptr"]),
                shape=tuple(d["shape"]),
            )
        return cls(W, **kwargs)


def stats(counts: np.ndarray, n_steps: int, dt: float = 1.0) -> dict:
    """Summarize a run() result: firing rates in Hz and active fraction.

    ``counts`` are spike counts accumulated over ``n_steps`` at spacing
    ``dt`` ms, i.e. a duration of ``n_steps * dt`` ms.
    """
    counts = np.asarray(counts)
    duration_s = n_steps * dt / 1000.0
    rates_hz = counts / duration_s
    return {
        "mean_rate_hz": float(np.mean(rates_hz)),
        "max_rate_hz": float(np.max(rates_hz)) if counts.size else 0.0,
        "active_frac": float(np.mean(counts > 0)) if counts.size else 0.0,
        "total_spikes": int(np.sum(counts)),
    }
