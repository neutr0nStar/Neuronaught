"""Tests for fly.sim.Reservoir: LIF dynamics on small synthetic graphs.

These use tiny hand-built CSR graphs (3-4 neurons) so they run in a
fraction of a second, but exercise the same code paths (both spmv
backends get calibrated/benchmarked internally regardless of N).
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from fly.sim import Reservoir, stats

DT = 1.0
DRIVE = 22.0  # matches fly.encode.DEFAULT_DRIVE derivation: ~100 Hz drive.


def make_chain(w01: float, w12: float) -> sp.csr_matrix:
    """3-neuron chain: 0 -> 1 -> 2. W[post, pre]."""
    dense = np.zeros((3, 3), dtype=np.float32)
    dense[1, 0] = w01
    dense[2, 1] = w12
    return sp.csr_matrix(dense)


def make_branch(w01: float, w02: float) -> sp.csr_matrix:
    """3-neuron branch: 0 -> 1 (w01), 0 -> 2 (w02). No 1->2 edge."""
    dense = np.zeros((3, 3), dtype=np.float32)
    dense[1, 0] = w01
    dense[2, 0] = w02
    return sp.csr_matrix(dense)


def run_manual(res: Reservoir, i_ext: np.ndarray, n_steps: int):
    """Step manually and return the full [n_steps, N] spike raster."""
    raster = np.zeros((n_steps, res.N), dtype=bool)
    for t in range(n_steps):
        raster[t] = res.step(i_ext)
    return raster


# ---------------------------------------------------------------------------
# Chain: driven neuron 0 fires ~100 Hz, propagates to 1 then 2.
# ---------------------------------------------------------------------------

def test_chain_drive_rate_and_propagation():
    # Weight chosen large enough that the synaptic current from a
    # ~100 Hz spike train (which decays substantially between pulses
    # at tau_syn=5ms, period ~10ms) still averages above the ~7 mV
    # needed to eventually cross threshold; see fly.encode module
    # docstring for the threshold-crossing derivation.
    W = make_chain(w01=30.0, w12=30.0)
    res = Reservoir(W, dt=DT, spmv_method="auto")
    n_steps = 1000
    i_ext = np.zeros(3, dtype=np.float32)
    i_ext[0] = DRIVE
    raster = run_manual(res, i_ext, n_steps)

    counts = raster.sum(axis=0)
    rate0 = counts[0] / (n_steps * DT / 1000.0)
    assert 80.0 <= rate0 <= 120.0, f"neuron 0 rate {rate0} Hz not within 20% of 100 Hz"
    assert counts[1] > 0, "neuron 1 never fired"
    assert counts[2] > 0, "neuron 2 never fired"

    first0 = np.flatnonzero(raster[:, 0])[0]
    first1 = np.flatnonzero(raster[:, 1])[0]
    first2 = np.flatnonzero(raster[:, 2])[0]
    assert first1 > first0, "neuron 1 must spike strictly after neuron 0"
    assert first2 > first1, "neuron 2 must spike strictly after neuron 1"


# ---------------------------------------------------------------------------
# Inhibition: a driven neuron receiving an inhibitory input from a
# spiking upstream neuron should fire less than an undriven-inhibition
# control (same driven neuron, no inhibitory edge present).
# ---------------------------------------------------------------------------

def test_inhibitory_edge_suppresses_firing():
    n_steps = 1000
    threshish_drive = 8.0  # just above the 7 mV bare threshold-crossing bound

    # Network with inhibition: 0 -> 1 excitatory (irrelevant here, just
    # keeps 0 spiking normally), 0 -> 2 inhibitory (-10 mV). Neuron 2 is
    # itself driven near threshold, and neuron 0 is driven hard so it
    # fires regularly and suppresses neuron 2 via the inhibitory edge.
    W_inhib = make_branch(w01=10.0, w02=-10.0)
    res_inhib = Reservoir(W_inhib, dt=DT, spmv_method="auto")
    i_ext_inhib = np.zeros(3, dtype=np.float32)
    i_ext_inhib[0] = DRIVE
    i_ext_inhib[2] = threshish_drive
    counts_inhib = res_inhib.run(i_ext_inhib, n_steps)

    # Control: identical driven neuron 2, but no inhibitory edge at all
    # (0 -> 2 weight is 0), so neuron 2's firing is unaffected by 0.
    W_control = make_branch(w01=10.0, w02=0.0)
    res_control = Reservoir(W_control, dt=DT, spmv_method="auto")
    i_ext_control = np.zeros(3, dtype=np.float32)
    i_ext_control[0] = DRIVE
    i_ext_control[2] = threshish_drive
    counts_control = res_control.run(i_ext_control, n_steps)

    assert counts_inhib[2] < counts_control[2], (
        f"inhibited neuron 2 fired {counts_inhib[2]} times, "
        f"control fired {counts_control[2]} times (expected inhibited < control)"
    )


# ---------------------------------------------------------------------------
# Determinism: no RNG in the dynamics -> identical runs give identical
# counts (checked for both explicit spmv backends).
# ---------------------------------------------------------------------------

def test_determinism_dense_and_gather():
    for method in ("dense", "gather", "auto"):
        W = make_chain(w01=10.0, w12=10.0)
        i_ext = np.array([DRIVE, 0.0, 0.0], dtype=np.float32)

        res_a = Reservoir(W, dt=DT, spmv_method=method, seed=1)
        counts_a = res_a.run(i_ext, 500)

        res_b = Reservoir(W, dt=DT, spmv_method=method, seed=1)
        counts_b = res_b.run(i_ext, 500)

        np.testing.assert_array_equal(counts_a, counts_b)


def test_reset_restores_initial_state():
    W = make_chain(w01=10.0, w12=10.0)
    res = Reservoir(W, dt=DT, spmv_method="dense")
    i_ext = np.array([DRIVE, 0.0, 0.0], dtype=np.float32)
    res.run(i_ext, 200)
    res.reset()
    assert np.all(res.v == res.v_rest)
    assert np.all(res.i_syn == 0.0)
    assert np.all(res.refrac_left == 0.0)
    assert not np.any(res._spikes_prev)


# ---------------------------------------------------------------------------
# Refractory period bounds the max firing rate.
# ---------------------------------------------------------------------------

def test_refractory_bounds_max_rate():
    W = sp.csr_matrix((1, 1), dtype=np.float32)
    refrac = 2.2
    res = Reservoir(W, dt=DT, refrac=refrac, spmv_method="dense")
    i_ext = np.array([1000.0], dtype=np.float32)  # huge drive: spike ASAP every time
    counts = res.run(i_ext, 1000)
    max_rate_hz = 1000.0 / refrac
    observed_rate_hz = counts[0] / (1000 * DT / 1000.0)
    assert observed_rate_hz <= max_rate_hz + 1e-6, (
        f"observed {observed_rate_hz} Hz exceeds theoretical max {max_rate_hz} Hz"
    )


# ---------------------------------------------------------------------------
# on_frame callback: called the right number of times, with uint32 payload.
# ---------------------------------------------------------------------------

def test_on_frame_called_correct_times_and_dtype():
    W = make_chain(w01=10.0, w12=10.0)
    res = Reservoir(W, dt=DT, spmv_method="dense")
    i_ext = np.array([DRIVE, 0.0, 0.0], dtype=np.float32)

    frames = []

    def on_frame(idx):
        frames.append(idx)

    n_steps = 100
    frame_every = 10
    res.run(i_ext, n_steps, frame_every=frame_every, on_frame=on_frame)

    assert len(frames) == n_steps // frame_every
    for f in frames:
        assert f.dtype == np.uint32


def test_run_with_count_idx_subset():
    W = make_chain(w01=10.0, w12=10.0)
    res = Reservoir(W, dt=DT, spmv_method="dense")
    i_ext = np.array([DRIVE, 0.0, 0.0], dtype=np.float32)
    n_steps = 500

    full_counts = Reservoir(W, dt=DT, spmv_method="dense").run(i_ext, n_steps)
    subset_counts = res.run(i_ext, n_steps, count_idx=np.array([2, 0]))

    assert subset_counts.shape == (2,)
    assert subset_counts[0] == full_counts[2]
    assert subset_counts[1] == full_counts[0]


def test_stats_helper_sane_on_driven_chain():
    W = make_chain(w01=10.0, w12=10.0)
    res = Reservoir(W, dt=DT, spmv_method="dense")
    i_ext = np.array([DRIVE, 0.0, 0.0], dtype=np.float32)
    n_steps = 1000
    counts = res.run(i_ext, n_steps)
    s = stats(counts, n_steps, dt=DT)
    assert s["total_spikes"] == int(counts.sum())
    assert 0.0 <= s["active_frac"] <= 1.0
    assert s["max_rate_hz"] >= s["mean_rate_hz"]
