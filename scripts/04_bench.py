"""Benchmark the LIF reservoir (fly.sim.Reservoir) on the full connectome.

Usage: uv run python scripts/04_bench.py

Skips gracefully (exit 0) if data/processed/graph.npz or io_groups.npz
haven't been produced yet by scripts/01_build_graph.py / 02_pick_io.py
-- those are built by a separate pipeline stage.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fly.encode import board_to_input, load_io  # noqa: E402
from fly.sim import Reservoir, stats  # noqa: E402

DATA = _ROOT / "data" / "processed"
GRAPH_PATH = DATA / "graph.npz"
IO_PATH = DATA / "io_groups.npz"


def bench_board(res: Reservoir, io: dict, board, label: str, drive: float,
                 n_steps_time: int = 200, n_steps_move: int = 300) -> None:
    N = res.N
    readout = io["readout"]
    i_ext = board_to_input(board, io, N, drive=drive)

    res.reset()
    t0 = time.perf_counter()
    res.run(i_ext, n_steps_time)
    ms_per_step = (time.perf_counter() - t0) / n_steps_time * 1e3

    res.reset()
    t0 = time.perf_counter()
    counts = res.run(i_ext, n_steps_move)
    ms_per_move = (time.perf_counter() - t0) * 1e3

    s = stats(counts, n_steps_move, dt=res.dt)
    active_frac = float(np.mean(counts > 0))
    readout_counts = counts[readout]
    n_readout_active = int(np.sum(readout_counts > 0))

    print(f"\n--- {label} (drive={drive}) ---")
    print(f"ms/step (n={n_steps_time} @ dt={res.dt}): {ms_per_step:.4f} ms")
    print(f"ms/move (n={n_steps_move} @ dt={res.dt}): {ms_per_move:.2f} ms")
    print(f"mean population rate: {s['mean_rate_hz']:.2f} Hz")
    print(f"max neuron rate: {s['max_rate_hz']:.2f} Hz")
    print(f"active fraction (>=1 spike): {active_frac * 100:.2f}%")
    print(f"readout neurons with >=1 spike: {n_readout_active}/{len(readout)}")

    if s["mean_rate_hz"] > 200.0:
        print(
            "  [WARNING] activity may be EXPLODING (mean pop. rate > 200 Hz). "
            "Suggestion: scale W by ~0.5 (or lower drive) -- not applied automatically."
        )
    if n_readout_active == 0:
        print(
            "  [WARNING] activity DIED OUT: no readout neuron ever spiked. "
            "Suggestion: raise drive, check nt_sign convention, or scale W up -- "
            "not applied automatically."
        )


def main() -> int:
    if not GRAPH_PATH.exists():
        print(f"[skip] {GRAPH_PATH} not found yet -- run 01_build_graph.py first.")
        return 0
    if not IO_PATH.exists():
        print(f"[skip] {IO_PATH} not found yet -- run 02_pick_io.py first.")
        return 0

    print(f"Loading graph from {GRAPH_PATH} ...")
    t0 = time.perf_counter()
    res = Reservoir.from_npz(GRAPH_PATH, dt=1.0)
    t_load = time.perf_counter() - t0
    N, nnz = res.N, res.W_csr.nnz
    print(f"N={N} nnz={nnz} (density={nnz / N / N:.2e})  load+calibration time={t_load:.2f}s")
    timings = res.spmv_timings_s or {}
    print(
        f"spmv method chosen: {res.spmv_method}  "
        f"(calibration: dense={timings.get('dense', float('nan')) * 1e3:.3f} ms/call, "
        f"gather={timings.get('gather', float('nan')) * 1e3:.3f} ms/call "
        f"at ~3% active fraction)"
    )

    io = load_io(IO_PATH)

    board = (1, 0, 0, 0, 2, 0, 0, 0, 0)
    empty_board = (0,) * 9

    bench_board(res, io, board, "sample board (1,0,0,0,2,0,0,0,0)", drive=22.0)
    bench_board(res, io, empty_board, "empty board (baseline)", drive=22.0)

    print("\n--- dt=0.5 timing check ---")
    res_half = Reservoir.from_npz(GRAPH_PATH, dt=0.5)
    print(f"spmv method chosen at dt=0.5: {res_half.spmv_method}")
    i_ext = board_to_input(board, io, N, drive=22.0)
    res_half.reset()
    n_steps = 400  # 400 * 0.5ms = 200ms, comparable window to the dt=1 checks
    t0 = time.perf_counter()
    res_half.run(i_ext, n_steps)
    dt_half = time.perf_counter() - t0
    print(f"ms/step at dt=0.5 (n={n_steps}): {dt_half / n_steps * 1e3:.4f} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main())
