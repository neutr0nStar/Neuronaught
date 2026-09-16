# Tuning

## Why the gain isn't 1

Shiu et al. 2024's parameters, taken as-is (gain 1), make our ≥5-synapse thresholded graph inhibition-dominated: driven visual neurons (Mi1, etc.) excite GABAergic Pm interneurons, which quickly silence them, and activity never reaches the central brain. This is a consequence of the edge threshold and graph construction here, not a claim about the real fly.

## Gain x bias sweep

300 ms runs, three boards, sweeping a global synaptic gain multiplier and a constant per-neuron bias current:

| gain | bias | active neurons | mean rate | active descending | ms/move |
|---|---|---|---|---|---|
| 1 | 0 | 0.1% | 0.07 Hz | 0 / 1308 | 113 |
| 1 | 4 mV | 19.5% | 9.4 Hz | 521 | 300 |
| **2** | **0** | **20.3%** | **14.0 Hz** | **557** | **388** |
| 3 | 0 | 25.2% | 20.1 Hz | 694 | 479 |
| 5 | 6 mV | 38.4% | 33.6 Hz | 819 | 658 |

**Gain 2, bias 0** was chosen: only vision drives the brain (no artificial "always on" current), activity is moderate and clearly board-dependent (not silent, not saturated), and a move costs about 0.4 s — acceptable for an interactive demo. Settings live in `fly/config.py` (`GAIN`, `BIAS`, `DRIVE`, `DT`, `N_STEPS`, `FRAME_EVERY`).

## How to retune

1. Edit `fly/config.py` (`GAIN`, `BIAS`, or `DRIVE`).
2. Re-run `uv run python scripts/04_bench.py` to see active-fraction / mean-rate / ms-per-move at the new settings (requires `graph.npz` and `io_groups.npz`).
3. If you want the readout to reflect the new dynamics, re-run `uv run python -u scripts/03_train_readout.py --regen` (forces feature recomputation instead of using the cached `features.npz`) to retrain against the new spike statistics.
4. Restart the server; it hot-reloads a freshly written `readout.npz` after each fly move without a restart, but simulation settings (`GAIN`/`BIAS`/`DRIVE`) are only read at startup.

## Ideas to improve

- Use more than 4,000 readout neurons in the "wide" feature set (`scripts/02_pick_io.py` / `scripts/03_train_readout.py`), trading training time and inference cost for more signal.
- Run a longer window than 300 ms, giving slower or more indirect pathways more time to influence descending neurons.
- Use a finer integration step (0.5 ms instead of 1 ms) for better fidelity to Shiu et al.'s 0.1 ms, at ~2x simulation cost.
