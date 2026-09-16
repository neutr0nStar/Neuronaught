"""Readout head: maps reservoir spike counts to a tic-tac-toe move.

Trained offline (by a script that doesn't exist yet) and saved to
``data/processed/readout.npz`` with keys:

    W            float32[F, 9]   linear map, features -> 9 move logits
    b            float32[9]      bias
    mu, sd       float32[F]      per-feature mean/std used to normalize
                                  log1p(spike counts) before the linear map
    feature      str             feature kind, expected "log1p_counts"
    readout_idx  int32[F]        raw neuron indices whose spike counts are the features
                                  (see fly.encode.load_io) feed the head,
                                  as positions into that array (F <= R)
    n_steps, dt, drive, frame_every
                 scalars describing the simulation the head was trained
                 against, so the server can reuse the exact same settings
                 at inference time.

If that file doesn't exist yet (training hasn't happened), `Readout.load`
returns None and the caller should fall back to `RandomReadout`, which
plays uniformly random legal moves with all-zero logits so the rest of
the pipeline (websocket protocol, UI, brain viewer) works end-to-end
before the fly is trained.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Optional

import numpy as np

from fly import config, game

logger = logging.getLogger(__name__)

# Large-but-finite "masked out" logit for occupied cells, rather than a
# real -inf: these logits get sent to the browser as JSON, and actual
# Infinity is not valid JSON (json.dumps emits a token JS can't parse).
_MASKED_LOGIT = -1.0e9


class Readout:
    """Linear readout: log1p(counts) -> normalize -> linear -> mask -> argmax."""

    trained = True

    def __init__(
        self,
        W: np.ndarray,
        b: np.ndarray,
        mu: np.ndarray,
        sd: np.ndarray,
        readout_idx: np.ndarray,
        feature: str = config.FEATURE,
        n_steps: int = config.N_STEPS,
        dt: float = config.DT,
        drive: float = config.DRIVE,
        frame_every: int = config.FRAME_EVERY,
    ):
        self.W = np.asarray(W, dtype=np.float32)
        self.b = np.asarray(b, dtype=np.float32)
        self.mu = np.asarray(mu, dtype=np.float32)
        self.sd = np.asarray(sd, dtype=np.float32)
        self.readout_idx = np.asarray(readout_idx, dtype=np.int64)
        self.feature = str(feature)
        self.n_steps = int(n_steps)
        self.dt = float(dt)
        self.drive = float(drive)
        self.frame_every = int(frame_every)

        if self.feature != config.FEATURE:
            logger.warning(
                "readout.npz feature=%r, but Readout.predict only implements "
                "log1p_counts; proceeding anyway.",
                self.feature,
            )

    @classmethod
    def load(cls, path) -> Optional["Readout"]:
        """Load a trained readout from ``path``. Returns None if missing."""
        path = Path(path)
        if not path.exists():
            return None
        with np.load(path, allow_pickle=True) as d:
            kwargs = dict(
                W=d["W"],
                b=d["b"],
                mu=d["mu"],
                sd=d["sd"],
                readout_idx=d["readout_idx"],
            )
            if "feature" in d.files:
                kwargs["feature"] = str(d["feature"])
            for key in ("n_steps", "dt", "drive", "frame_every"):
                if key in d.files:
                    kwargs[key] = np.asarray(d[key]).item()
        return cls(**kwargs)

    def predict(self, counts_readout: np.ndarray, board) -> tuple[int, list[float]]:
        """Pick a move from spike counts of the readout neurons.

        ``counts_readout`` must be the reservoir counts for exactly
        ``self.readout_idx`` (raw neuron indices), i.e. the server runs
        ``reservoir.run(..., count_idx=readout.readout_idx)``.
        """
        legal = game.legal_moves(board)
        if not legal:
            raise ValueError("predict called on a terminal board (no legal moves)")

        counts = np.asarray(counts_readout, dtype=np.float32)
        if counts.shape[0] != self.readout_idx.shape[0]:
            raise ValueError(
                f"expected counts for {self.readout_idx.shape[0]} readout neurons, got {counts.shape[0]}; "
                "run the reservoir with count_idx=readout.readout_idx")
        sd = np.where(self.sd == 0, np.float32(1.0), self.sd)
        feat = (np.log1p(counts) - self.mu) / sd
        logits = (feat @ self.W + self.b).astype(np.float64)

        masked = logits.copy()
        for i, v in enumerate(board):
            if v != game.EMPTY:
                masked[i] = _MASKED_LOGIT

        cell = int(np.argmax(masked))
        return cell, masked.tolist()


class RandomReadout:
    """Fallback used when no trained readout.npz exists yet.

    Plays a uniformly random legal move and reports all-zero logits, so
    the server/websocket/UI pipeline can be exercised end-to-end before
    the training script (and possibly the full reservoir sim) exist.
    """

    trained = False
    n_steps = config.N_STEPS
    dt = config.DT
    drive = config.DRIVE
    frame_every = config.FRAME_EVERY

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        logger.warning(
            "No trained readout found (data/processed/readout.npz missing) - "
            "the fly is UNTRAINED and will play uniformly random legal moves."
        )

    def predict(self, counts_readout: np.ndarray, board) -> tuple[int, list[float]]:
        legal = game.legal_moves(board)
        if not legal:
            raise ValueError("predict called on a terminal board (no legal moves)")
        cell = self.rng.choice(legal)
        return cell, [0.0] * 9
