# Model

## LIF dynamics (as implemented in `fly/sim.py`)

Exponential-current-synapse LIF, exponential-Euler integration, one implicit
step of synaptic delay (a spike affects `i_syn` on the *next* step):

```
i_syn <- i_syn * exp(-dt/tau_syn) + W @ spikes_prev
v     <- v + (dt/tau_mem) * (v_rest - v + i_syn + i_ext)   [if not refractory]
v     <- v_reset                                           [if refractory]
refrac_left <- max(refrac_left - dt, 0)
spiked = (not refractory) & (v >= v_thresh)
v[spiked] = v_reset ; refrac_left[spiked] = refrac
```

`W` is the signed, synapse-count-weighted connectome graph (`docs/DATA.md`); `w` per synapse is already baked into `W`, scaled by `config.GAIN`.

## Parameters: Shiu et al. 2024 vs. this project

| Parameter | Shiu et al. 2024 | This project |
|---|---|---|
| `dt` (integration step) | 0.1 ms | **1 ms** |
| Synaptic/axonal delays | modeled | **dropped** (instantaneous, one implicit step) |
| Global synaptic gain | 1.0 (baseline) | **2.0** (see `docs/TUNING.md`) |
| τ_mem | 20 ms | 20 ms |
| τ_syn | 5 ms | 5 ms |
| v_rest | −52 mV | −52 mV |
| v_thresh | −45 mV | −45 mV |
| v_reset | −52 mV | −52 mV |
| refractory | 2.2 ms | 2.2 ms |
| synaptic weight | 0.275 mV × synapse count | 0.275 mV × synapse count × gain |

Weights are clipped to ±20 mV (`W_CLIP`, `scripts/01_build_graph.py`). Simulation length is `N_STEPS = 300` steps of `DT = 1.0` ms = 300 ms of simulated brain time per move; a spike frame is streamed every `FRAME_EVERY = 10` steps (30 frames/move).

## Encoding: the 22 mV drive

Driven visual input neurons receive a constant external current `DRIVE = 22.0 mV`, derived in `fly/encode.py` from the LIF constants to target ~100 Hz firing in isolation (no recurrent input):

- Steady-state subthreshold voltage under constant `i_ext`: `v_ss = v_rest + i_ext` (from `dv/dt = 0`).
- To ever reach threshold: `i_ext > v_thresh - v_rest = 7 mV`.
- Subthreshold charging trajectory from reset: `v(t) = v_rest + i_ext * (1 - exp(-t/tau_mem))`, so time to threshold is `t_thresh = -tau_mem * ln(1 - 7/i_ext)`.
- For a 100 Hz target (10 ms period) minus the 2.2 ms refractory period, the charging budget is 7.8 ms: `7.8 = -20 * ln(1 - 7/i_ext) => i_ext ≈ 21.7 mV`, rounded up to **22.0 mV**.

Undriven neurons (including empty board cells) get `i_ext = 0`. `config.BIAS` (default 0) can additionally add a constant sub-threshold current to *every* neuron via the reservoir's `i_drive`, independent of the board — see `docs/TUNING.md`.

## Determinism

The simulation has **no randomness**: `Reservoir.reset()` sets every neuron to `v_rest`, zero synaptic current, zero refractory time, and no prior spikes, before every query. Given the same board (and hence the same `i_ext`), the LIF update above is a deterministic function of state, so the same board always produces the same spike trains, counts, and move — there is no seeded RNG in the per-step dynamics (the `spmv_method="auto"` calibration step and neuron/feature *selection* scripts do use a seeded RNG, but not the running simulation itself).
