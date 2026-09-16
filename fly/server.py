"""FastAPI server for "The Fly Brain Plays Tic-Tac-Toe".

Wires together:
  - fly.sim.Reservoir: the LIF spiking simulation over the male fly
    connectome graph (or FakeReservoir, a fast stand-in enabled by
    FLY_FAKE_SIM=1, for smoke-testing before the real 140k-neuron sim
    run is fast/ready or the readout is trained).
  - fly.encode: board -> external drive current, io group definitions.
  - fly.readout: reservoir spike counts -> move logits.
  - fly.game: tic-tac-toe rules/state.
  - web/: the static frontend (three.js brain viewer + board UI).

Run with:
    uv run python -m fly.server
or:
    uv run uvicorn fly.server:app --port 8000

Set FLY_FAKE_SIM=1 to replace the reservoir with a fast fake (random
sparse spike frames, random counts) so the server can be exercised
without the full connectome simulation or a trained readout.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import numpy as np
import scipy.sparse as sp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from fly import config, encode, game
from fly.readout import RandomReadout, Readout
from fly.sim import Reservoir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fly.server")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
WEB_DIR = ROOT / "web"

FAKE_SIM = os.environ.get("FLY_FAKE_SIM") == "1"


class FakeReservoir:
    """Fast stand-in for fly.sim.Reservoir (FLY_FAKE_SIM=1).

    Emits random sparse spike frames and random spike counts, matching
    Reservoir's reset()/run() interface, so the server (websocket
    protocol, frame streaming, readout wiring) can be smoke-tested
    without the real 140k-neuron simulation.
    """

    def __init__(self, n: int, seed: int = 0):
        self.N = n
        self._rng = np.random.default_rng(seed)

    def reset(self) -> None:
        pass

    def run(self, i_ext, n_steps, frame_every=0, on_frame=None, count_idx=None):
        n_frames = (n_steps // frame_every) if frame_every else 0
        for _ in range(n_frames):
            k = int(self._rng.integers(20, 80))
            idx = self._rng.choice(self.N, size=k, replace=False).astype(np.uint32)
            if on_frame is not None:
                on_frame(np.sort(idx))
        size = self.N if count_idx is None else len(count_idx)
        return self._rng.integers(0, 5, size=size).astype(np.int32)


class AppState:
    """Process-global state populated at startup (lifespan)."""

    def __init__(self):
        self.reservoir = None
        self.io: dict = {}
        self.n = 0
        self.xyz_bytes = b""
        self.superclass_b64 = ""
        self.superclass_names: list[str] = []
        self.readout: Optional[object] = None
        # Simulation settings: fly.config values are the source of truth;
        # a trained readout.npz may override any of these (see lifespan()).
        self.n_steps = config.N_STEPS
        self.dt = config.DT
        self.drive = config.DRIVE
        self.frame_every = config.FRAME_EVERY
        self.gain = config.GAIN
        self.bias = config.BIAS
        self.lock = asyncio.Lock()


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    neurons_path = DATA_DIR / "neurons.npz"
    io_path = DATA_DIR / "io_groups.npz"
    readout_path = DATA_DIR / "readout.npz"
    graph_path = DATA_DIR / "graph.npz"

    with np.load(neurons_path, allow_pickle=True) as d:
        xyz = np.ascontiguousarray(d["xyz"], dtype=np.float32)
        superclass = np.ascontiguousarray(d["superclass"], dtype=np.uint8)
        state.superclass_names = [str(s) for s in d["superclass_names"]]
    state.n = xyz.shape[0]
    state.xyz_bytes = xyz.tobytes(order="C")
    state.superclass_b64 = base64.b64encode(superclass.tobytes()).decode("ascii")

    state.io = encode.load_io(io_path)

    rd = Readout.load(readout_path)
    if rd is None:
        rd = RandomReadout()
    else:
        state.n_steps = rd.n_steps
        state.dt = rd.dt
        state.drive = rd.drive
        state.frame_every = rd.frame_every
    state.readout = rd

    if FAKE_SIM:
        logger.warning("FLY_FAKE_SIM=1: using a fake reservoir, NOT the real connectome sim.")
        state.reservoir = FakeReservoir(state.n)
    else:
        # Reservoir.from_npz doesn't support scaling the weights, so load
        # the CSR graph ourselves and apply config.GAIN to W before
        # constructing. config.BIAS becomes the reservoir's constant
        # per-step i_drive baseline (added to whatever i_ext board_to_input
        # produces each step - see fly.sim.Reservoir.step), which is
        # equivalent to adding it into i_ext directly but avoids rebuilding
        # an [N] array every move.
        with np.load(graph_path) as d:
            W = sp.csr_matrix((d["data"], d["indices"], d["indptr"]), shape=tuple(d["shape"]))
        W.data = (W.data * state.gain).astype(np.float32)
        i_drive = np.full(state.n, state.bias, dtype=np.float32) if state.bias else None
        state.reservoir = Reservoir(W, dt=state.dt, i_drive=i_drive)

    logger.info(
        "fly server ready: n=%d, trained=%s, n_steps=%d, dt=%.2f, drive=%.1f, "
        "frame_every=%d, gain=%.2f, bias=%.2f",
        state.n,
        getattr(state.readout, "trained", False),
        state.n_steps,
        state.dt,
        state.drive,
        state.frame_every,
        state.gain,
        state.bias,
    )
    yield


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# HTTP API (must be registered before the catch-all static mount below)
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/meta")
async def api_meta():
    io = state.io
    return {
        "n": state.n,
        "xyz_url": "/api/xyz",
        "superclass": state.superclass_b64,
        "superclass_names": state.superclass_names,
        "input_groups": {
            "X": [arr.tolist() for arr in io["input_X"]],
            "O": [arr.tolist() for arr in io["input_O"]],
        },
        "readout": io["readout"].tolist(),
        "sim": {
            "n_steps": state.n_steps,
            "dt": state.dt,
            "drive": state.drive,
            "frame_every": state.frame_every,
            "gain": state.gain,
            "bias": state.bias,
            "trained": bool(getattr(state.readout, "trained", False)),
        },
    }


@app.get("/api/xyz")
async def api_xyz():
    return Response(content=state.xyz_bytes, media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# WebSocket game loop
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    conn = {
        "board": (game.EMPTY,) * 9,
        "human": game.X,
        "fly": game.O,
        "thinking": False,
    }

    async def send_state(thinking: bool) -> None:
        await ws.send_json(
            {
                "type": "state",
                "board": list(conn["board"]),
                "status": game.status(conn["board"]),
                "human": conn["human"],
                "fly": conn["fly"],
                "thinking": thinking,
            }
        )

    async def do_fly_move() -> None:
        board = conn["board"]
        if game.is_terminal(board):
            return

        conn["thinking"] = True
        await send_state(True)

        i_ext = encode.board_to_input(board, state.io, state.n, drive=state.drive)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_frame(idx: np.ndarray) -> None:
            frame_bytes = idx.astype(np.uint32).tobytes()
            loop.call_soon_threadsafe(queue.put_nowait, frame_bytes)

        async def sender() -> None:
            while True:
                item = await queue.get()
                if item is None:
                    return
                await ws.send_bytes(item)

        sender_task = asyncio.create_task(sender())
        try:
            async with state.lock:
                state.reservoir.reset()
                counts_readout = await asyncio.to_thread(
                    state.reservoir.run,
                    i_ext,
                    state.n_steps,
                    state.frame_every,
                    on_frame,
                    getattr(state.readout, "readout_idx", state.io["readout"]),
                )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)
            await sender_task

        # Hot-reload: if the fly was untrained at startup and readout.npz has since
        # been written by scripts/03_train_readout.py, pick it up without a restart.
        if not getattr(state.readout, "trained", False):
            rd = Readout.load(DATA_DIR / "readout.npz")
            if rd is not None:
                logger.info("loaded freshly trained readout (heldout=%s)", getattr(rd, "heldout_rate", "?"))
                state.readout = rd
        cell, logits = state.readout.predict(counts_readout, board)
        conn["board"] = game.play(board, cell)
        conn["thinking"] = False
        await ws.send_json({"type": "fly_move", "cell": cell, "logits": logits})
        await send_state(False)

    async def handle_new_game(msg: dict) -> None:
        fly_first = bool(msg.get("fly_first", False))
        conn["board"] = (game.EMPTY,) * 9
        conn["thinking"] = False
        conn["fly"] = game.X if fly_first else game.O
        conn["human"] = game.O if fly_first else game.X
        await send_state(False)
        if fly_first:
            await do_fly_move()

    async def handle_human_move(msg: dict) -> None:
        if conn["thinking"]:
            return  # ignore moves while the fly is thinking
        board = conn["board"]
        if game.is_terminal(board):
            await ws.send_json({"type": "error", "message": "game is over"})
            return
        cell = msg.get("cell")
        if not isinstance(cell, int) or not (0 <= cell < 9):
            await ws.send_json({"type": "error", "message": f"invalid cell: {cell!r}"})
            return
        if game.to_move(board) != conn["human"]:
            await ws.send_json({"type": "error", "message": "not your turn"})
            return
        if board[cell] != game.EMPTY:
            await ws.send_json({"type": "error", "message": "cell is occupied"})
            return

        conn["board"] = game.play(board, cell)
        await send_state(False)
        if not game.is_terminal(conn["board"]):
            await do_fly_move()

    try:
        await send_state(False)
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")
            try:
                if mtype == "new_game":
                    await handle_new_game(msg)
                elif mtype == "human_move":
                    await handle_human_move(msg)
                else:
                    await ws.send_json({"type": "error", "message": f"unknown message type: {mtype!r}"})
            except Exception as exc:  # noqa: BLE001 - report to client, keep connection alive
                conn["thinking"] = False
                logger.exception("error handling message %r", msg)
                await ws.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Static frontend. Mounted last so the API routes above take precedence.
# "/static" gives web/app.js etc. an explicit prefix; the root mount serves
# index.html, style.css, and the *.js modules at the plain paths index.html
# references them by (e.g. href="style.css", src="app.js").
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fly.server:app", host="127.0.0.1", port=8000)
