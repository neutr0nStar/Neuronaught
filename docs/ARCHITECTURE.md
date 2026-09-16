# Architecture

## Layout

| Path | Contents |
|---|---|
| `scripts/` | data download, graph build, input/readout selection, training, bench |
| `fly/sim.py` | LIF reservoir (SciPy CSR; column-gather update wins over dense spmv ~4.7x at this sparsity, ~0.3 ms/step) |
| `fly/encode.py` | board → input current; input/readout group loading |
| `fly/game.py` | tic-tac-toe rules + minimax |
| `fly/readout.py` | ridge readout (`Readout`) and untrained fallback (`RandomReadout`) |
| `fly/server.py` | FastAPI + WebSocket server |
| `fly/config.py` | shared simulation settings (gain, bias, drive, dt, steps) |
| `web/` | plain HTML/CSS/JS, three.js 0.186 via CDN importmap |

## Request flow, per turn

1. Client sends a WebSocket JSON message (`human_move` or `new_game`).
2. `fly/server.py` updates the board, and if it's the fly's turn calls `do_fly_move()`.
3. `fly.encode.board_to_input` turns the board into a per-neuron external drive current (`i_ext`, float32[N]).
4. The server resets the reservoir and runs it for `N_STEPS` (300) inside a worker thread (`asyncio.to_thread`) so the event loop stays free — `Reservoir.run(i_ext, n_steps, frame_every, on_frame, count_idx)`.
5. Every `FRAME_EVERY` (10) ms of simulated time, `on_frame` is called with the sorted neuron indices that spiked since the last frame; the server pushes each frame to the client immediately as a binary WebSocket message via an `asyncio.Queue` + sender task, so the brain view animates while the sim is still running.
6. After the run, spike counts restricted to the readout neuron indices (`count_idx`) go to `fly.readout.Readout.predict`, which normalizes `log1p(counts)`, applies the trained linear map, masks occupied cells, and argmaxes to a cell.
7. The server plays that move and sends a `fly_move` message, then a `state` message.

A shared `asyncio.Lock` (`state.lock`) serializes reservoir runs across concurrent connections, since there is one `Reservoir` instance per server process.

## WebSocket / HTTP protocol

### HTTP

| Endpoint | Returns |
|---|---|
| `GET /` | `web/index.html` |
| `GET /api/meta` | JSON: neuron count `n`, `xyz_url`, base64 `superclass` array + `superclass_names`, `input_groups.X`/`.O` (9 index lists each), `readout` (descending-neuron indices), `sim` (n_steps, dt, drive, frame_every, gain, bias, trained) |
| `GET /api/xyz` | raw bytes: float32[N, 3] soma positions, row-major, no header |

### WebSocket `/ws`

Client → server (JSON text frames):

| `type` | Fields | Meaning |
|---|---|---|
| `new_game` | `fly_first: bool` | reset the board; fly moves first if true |
| `human_move` | `cell: int (0-8)` | play a cell as the human |

Server → client:

- JSON text frames:
  - `{"type": "state", "board": [...], "status": ..., "human": ..., "fly": ..., "thinking": bool}` — sent after every board change.
  - `{"type": "fly_move", "cell": int, "logits": [9 floats]}` — the fly's chosen move and its (masked) readout logits.
  - `{"type": "error", "message": str}` — invalid move, wrong turn, etc.
- Binary frames: one per activity frame during a fly move, `uint32[]` little-endian, the sorted indices of neurons that spiked in that 10 ms window (no length prefix — the frame length is the message length / 4). 30 frames per move (300 ms / 10 ms).

`board` values: 0 = empty, 1 = X, 2 = O. `status` ∈ `{x_to_move, o_to_move, x_wins, o_wins, draw}`.

`FLY_FAKE_SIM=1` swaps in `FakeReservoir`, which emits random sparse frames and random counts with the same interface, so the whole protocol above can be exercised without the real connectome or a trained readout. `?mock=1` on the client skips the backend entirely and fakes both the meta/xyz fetch and the WS messages in-browser.

## Performance

- `fly.sim.Reservoir` picks between a dense CSR sparse matvec and a "gather" update (slice out spiking presynaptic columns from a CSC copy of the weight matrix, then `np.bincount` scatter-add) by benchmarking both at startup (`spmv_method="auto"`). At the sparsity and activity level this project runs at (~20% active, single-digit-to-low-double-digit Hz), gather wins, at roughly **0.3 ms/step**.
- A full move (300 steps, 140,024 neurons, 5.5M edges) takes about **0.37 s** wall-clock on an Apple M4, including streaming 30 binary activity frames over the WebSocket.
- See `docs/TUNING.md` for how gain/bias affect activity level and per-move latency.
