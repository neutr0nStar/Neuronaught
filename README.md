# Are you smarter than a fruit fly? 🪰

A real fruit-fly connectome — the **Male CNS v1.0**, released by Janelia FlyEM,
the University of Cambridge, and Google Research — simulated neuron by neuron
on a laptop. Show it a tic-tac-toe board and it picks a move, while you watch
its 140,024 neurons fire in a live, rotatable 3D brain.

<!-- TODO: add a screenshot of the two panels at docs/img/screenshot.png and reference it here -->

## How it works, in 6 lines

1. Your tic-tac-toe board...
2. ...is projected onto the fly's right eye (X = bright spot, O = dark spot).
3. The whole brain runs for 300 ms of simulated brain time.
4. We count spikes from 4,000 especially board-sensitive neurons.
5. A small trained linear readout turns those counts into a score per square.
6. The fly plays the highest-scoring empty square.

## What's real vs. engineered

- Real: the full wiring (140,024 neurons, 5.5M signed synaptic connections), every neuron's real soma position, connection signs from predicted neurotransmitters, and LIF spiking dynamics fit to this connectome by Shiu et al. 2024.
- Real: the retinotopic hex-column addresses used to place the board on the fly's eye.
- Engineered: a global synaptic gain of 2x (at the literature's gain of 1, activity dies out within two synaptic hops — see `docs/TUNING.md`), a coarser 1 ms integration step, and dropped synaptic delays.
- Engineered: the move itself is a linear readout trained purely to play tic-tac-toe, layered on top of the untouched biological network.

## Quickstart

Prerequisites: macOS or Linux, Python 3.12 via [uv](https://docs.astral.sh/uv/), ~600 MB free for the connectome download, 16 GB RAM.

```bash
uv venv --python 3.12 && uv pip install -e .
uv run python scripts/00_download.py        # ~560 MB from the public GCS bucket
uv run python scripts/01_build_graph.py     # -> data/processed/graph.npz, neurons.npz
uv run python scripts/02_pick_io.py         # -> io_groups.npz (input + readout neurons)
uv run python -u scripts/03_train_readout.py   # ~15 min on an M4 -> readout.npz
uv run uvicorn fly.server:app --port 8000   # open http://127.0.0.1:8000
```

A trained readout is already included at `data/processed/readout.npz`, so you
can skip the training step and jump straight to playing.

`uv run pytest` runs the unit tests. `FLY_FAKE_SIM=1` runs the server with a
fake reservoir (no connectome or trained readout needed), and
`http://127.0.0.1:8000/?mock=1` runs the page with no backend at all — both
are for testing without the real data.

## Results

- **0.836** optimal-move rate on held-out boards, vs. **0.709** for the same linear model on the raw board with no brain at all.
- **93%** win-or-draw rate against a random opponent.
- **~0.4 s** per fly move (300 ms of simulated brain time, plus streaming).

Full tables and methodology: [`docs/RESULTS.md`](docs/RESULTS.md).

## Learn more

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — file layout, request flow, WebSocket/HTTP protocol, performance
- [`docs/DATA.md`](docs/DATA.md) — connectome files, neuron set, edge thresholds, input/readout selection
- [`docs/MODEL.md`](docs/MODEL.md) — LIF equations, parameters, encoding math, determinism
- [`docs/RESULTS.md`](docs/RESULTS.md) — full results and runtime tables
- [`docs/TUNING.md`](docs/TUNING.md) — the gain/bias sweep and how to retune
- In-app explainer and pitch deck: run the server and visit `/explain.html`

## Credits

Male CNS v1.0 connectome: Janelia FlyEM, University of Cambridge, Google
Research — [male-cns.janelia.org](https://male-cns.janelia.org) (CC-BY). LIF
model: Shiu et al. 2024, *Nature* — [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model).
3D viewer: [three.js](https://threejs.org/). Images: Wikimedia Commons (see
`/explain.html` for individual photo/diagram credits). Code is MIT-licensed
(see `LICENSE`); the connectome data is CC-BY and downloaded separately.

Honest caveat: the fly does not know tic-tac-toe. The readout knows; the
brain computes.
