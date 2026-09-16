"""Train a linear readout head: reservoir spike counts -> tic-tac-toe move.

Pipeline:
  1. Generate features for every non-terminal board (fly.game.training_states,
     4520 boards): run the LIF reservoir (fly.sim.Reservoir) driven by
     fly.encode.board_to_input for fly.config.N_STEPS steps, and record
     spike counts over (a) the 1308 "descending" readout neurons
     (fly.encode.load_io) and (b) a K=4000 "wide" set of the highest-
     variance non-input neurons (candidate set picked from the first 200
     boards). Uses a multiprocessing.Pool of 6 workers, each loading the
     connectome weight matrix once. Checkpoints to
     data/processed/features.npz (pass --regen to force recomputation).
  2. Fit RidgeCV (5-fold, alphas log-spaced 1e-2..1e4) on log1p(counts),
     standardized, against 9-dim multi-hot optimal-move targets
     (fly.game.optimal_move_targets), for three feature variants:
       A: readout-only counts (F=1308)
       B: wide counts (F=4000)
       C: baseline -- raw 27-dim one-hot board, no brain at all
     evaluated on a seeded 80/20 held-out split via "optimal-move rate"
     (argmax over legal cells lands in the optimal-move set).
  3. Pick the best of A/B (prefer A if within 2 points of B -- keeps the
     "descending neurons" story). ``readout_idx`` are raw neuron indices.
     Refit on all 4520 boards and save data/processed/readout.npz.
  4. Play-evaluate the saved readout against fly.game.random_player and
     fly.game.minimax_player, both sides, using the same Pool.

Usage:
    uv run python scripts/03_train_readout.py [--regen] [--workers N]
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fly import config, game  # noqa: E402
from fly.encode import board_to_input, load_io  # noqa: E402
from fly.sim import Reservoir  # noqa: E402

DATA = _ROOT / "data" / "processed"
GRAPH_PATH = DATA / "graph.npz"
IO_PATH = DATA / "io_groups.npz"
FEATURES_PATH = DATA / "features.npz"
READOUT_PATH = DATA / "readout.npz"

N_WORKERS = 6
WIDE_K = 4000
WIDE_CANDIDATE_BOARDS = 200
ALPHAS = np.logspace(-2, 4, 13)
SD_FLOOR = 1e-3
TEST_FRAC = 0.2
SPLIT_SEED = 0
PREFER_A_MARGIN = 0.02  # prefer variant A unless B beats it by more than this

N_GAMES_RANDOM = 200
N_GAMES_MINIMAX = 20
PLAY_SEED = 12345

# ---------------------------------------------------------------------------
# Worker globals (populated once per process by _init_worker).
# ---------------------------------------------------------------------------
_worker_res: Reservoir | None = None
_worker_io: dict | None = None
_worker_readout: dict | None = None



def q_targets(board):
    """Per-cell minimax value for the player to move; illegal cells get -1."""
    q = np.full(9, -1.0, dtype=np.float32)
    for m in game.legal_moves(board):
        nb = game.play(board, m)
        v, _ = game.minimax(nb)      # value from the perspective of the player to move at nb
        q[m] = -v
    return q

def _load_scaled_W(graph_path, gain: float) -> sp.csr_matrix:
    with np.load(graph_path) as d:
        W = sp.csr_matrix((d["data"], d["indices"], d["indptr"]), shape=tuple(d["shape"]))
    if gain != 1.0:
        W = (W * gain).tocsr()
    return W


def _init_worker(graph_path, io_path, gain, dt):
    global _worker_res, _worker_io, _worker_readout
    W = _load_scaled_W(graph_path, gain)
    _worker_io = load_io(io_path)
    _worker_res = Reservoir(W, dt=dt)
    _worker_readout = None  # lazily loaded by _play_task, once per worker


def _run_board_task(args):
    """One board -> spike counts. mode='full' returns the full N-vector
    (used for the first WIDE_CANDIDATE_BOARDS boards, to pick the wide
    index set); mode='combined' returns (counts_ro, counts_wide) using a
    single simulation run with count_idx = readout ++ wide_idx."""
    idx, board, mode, extra = args
    assert _worker_res is not None and _worker_io is not None
    i_ext = board_to_input(board, _worker_io, _worker_res.N, drive=config.DRIVE) + config.BIAS
    _worker_res.reset()
    if mode == "full":
        counts = _worker_res.run(i_ext, config.N_STEPS)
        return idx, counts.astype(np.int32)
    combined_idx, n_readout = extra
    counts = _worker_res.run(i_ext, config.N_STEPS, count_idx=combined_idx)
    counts_ro = counts[:n_readout].astype(np.int16)
    counts_wide = counts[n_readout:].astype(np.int16)
    return idx, counts_ro, counts_wide


def _play_task(args):
    """Play one full game with the trained readout as one side."""
    game_id, opponent, fly_side, seed = args
    global _worker_readout
    assert _worker_res is not None and _worker_io is not None
    if _worker_readout is None:
        with np.load(READOUT_PATH, allow_pickle=True) as d:
            _worker_readout = {k: d[k] for k in d.files}
    rd = _worker_readout
    variant = str(rd["variant"])
    n_steps = int(rd["n_steps"])
    drive = float(rd["drive"])
    bias = float(rd["bias"])
    sd = np.where(rd["sd"] == 0, np.float32(1.0), rd["sd"])

    def fly_player(board, _rng):
        i_ext = board_to_input(board, _worker_io, _worker_res.N, drive=drive) + bias
        _worker_res.reset()
        counts = _worker_res.run(i_ext, n_steps, count_idx=rd["readout_idx"])
        feat = (np.log1p(counts.astype(np.float32)) - rd["mu"]) / sd
        logits = feat @ rd["W"] + rd["b"]
        legal = game.legal_moves(board)
        best_cell = max(legal, key=lambda c: logits[c])
        return best_cell

    opp_fn = game.random_player if opponent == "random" else game.minimax_player
    rng = random.Random(seed)
    if fly_side == game.X:
        winner = game.play_match(fly_player, opp_fn, rng)
    else:
        winner = game.play_match(opp_fn, fly_player, rng)
    return opponent, fly_side, winner


# ---------------------------------------------------------------------------
# Step 1: feature generation
# ---------------------------------------------------------------------------
def generate_features(pool, io, regen: bool):
    if FEATURES_PATH.exists() and not regen:
        print(f"[features] loading checkpoint {FEATURES_PATH}")
        with np.load(FEATURES_PATH) as d:
            return d["boards"], d["counts_ro"], d["counts_wide"], d["wide_idx"]

    boards = game.training_states()
    n_boards = len(boards)
    print(f"[features] {n_boards} training boards; generating with {N_WORKERS} workers ...")
    boards_arr = np.array(boards, dtype=np.int8)

    readout = io["readout"]
    n_readout = readout.shape[0]

    # --- Phase A: full-N counts for the first WIDE_CANDIDATE_BOARDS boards,
    # used only to pick the K=4000 highest-variance non-input neurons.
    t0 = time.perf_counter()
    n_candidates = min(WIDE_CANDIDATE_BOARDS, n_boards)
    tasks_a = [(i, boards[i], "full", None) for i in range(n_candidates)]
    N = None
    full_counts = None
    done = 0
    for idx, counts in pool.imap_unordered(_run_board_task, tasks_a, chunksize=4):
        if full_counts is None:
            N = counts.shape[0]
            full_counts = np.zeros((n_candidates, N), dtype=np.int32)
        full_counts[idx] = counts
        done += 1
        if done % 50 == 0:
            print(f"[features] phase A: {done}/{n_candidates} boards "
                  f"({time.perf_counter() - t0:.1f}s)")
    print(f"[features] phase A done in {time.perf_counter() - t0:.1f}s")

    input_neurons = np.unique(
        np.concatenate([*io["input_X"], *io["input_O"]]).astype(np.int64)
    )
    var = full_counts.var(axis=0)
    var[input_neurons] = -1.0
    order = np.argsort(-var)
    wide_idx = np.sort(order[:WIDE_K]).astype(np.int64)
    print(f"[features] picked {wide_idx.shape[0]} wide neurons "
          f"(variance range {var[wide_idx].min():.2f}..{var[wide_idx].max():.2f})")

    combined_idx = np.concatenate([readout, wide_idx]).astype(np.int64)

    counts_ro = np.zeros((n_boards, n_readout), dtype=np.int16)
    counts_wide = np.zeros((n_boards, WIDE_K), dtype=np.int16)
    # Slice the already-computed full counts for the candidate boards
    # instead of re-simulating them.
    counts_ro[:n_candidates] = full_counts[:, readout]
    counts_wide[:n_candidates] = full_counts[:, wide_idx]
    del full_counts

    # --- Phase B: remaining boards, single run each via combined_idx.
    remaining = [
        (i, boards[i], "combined", (combined_idx, n_readout))
        for i in range(n_candidates, n_boards)
    ]
    t1 = time.perf_counter()
    done = 0
    for idx, ro, wide in pool.imap_unordered(_run_board_task, remaining, chunksize=4):
        counts_ro[idx] = ro
        counts_wide[idx] = wide
        done += 1
        if done % 500 == 0:
            elapsed = time.perf_counter() - t1
            rate = done / elapsed
            eta = (len(remaining) - done) / rate if rate > 0 else float("nan")
            print(f"[features] phase B: {done}/{len(remaining)} boards "
                  f"({elapsed:.1f}s, eta {eta:.1f}s)")
    print(f"[features] phase B done in {time.perf_counter() - t1:.1f}s")
    print(f"[features] total feature generation: {time.perf_counter() - t0:.1f}s")

    np.savez(
        FEATURES_PATH,
        boards=boards_arr,
        counts_ro=counts_ro,
        counts_wide=counts_wide,
        wide_idx=wide_idx,
    )
    print(f"[features] checkpoint saved to {FEATURES_PATH}")
    return boards_arr, counts_ro, counts_wide, wide_idx


# ---------------------------------------------------------------------------
# Step 2/3: fit + evaluate
# ---------------------------------------------------------------------------
def board_onehot(boards: np.ndarray) -> np.ndarray:
    """boards: int8[M,9] in {0,1,2} -> float32[M,27] one-hot per cell."""
    m = boards.shape[0]
    oh = np.zeros((m, 9, 3), dtype=np.float32)
    rows = np.arange(m)[:, None]
    cols = np.arange(9)[None, :]
    oh[rows, cols, boards.astype(np.int64)] = 1.0
    return oh.reshape(m, 27)


def standardize(X: np.ndarray, mu=None, sd=None):
    if mu is None:
        mu = X.mean(axis=0)
    if sd is None:
        sd = X.std(axis=0)
    sd = np.maximum(sd, SD_FLOOR).astype(np.float32)
    mu = mu.astype(np.float32)
    return (X - mu) / sd, mu, sd


def optimal_move_rate(logits: np.ndarray, boards: np.ndarray, Y: np.ndarray) -> float:
    masked = logits.copy()
    masked[boards != 0] = -1e9
    pred = masked.argmax(axis=1)
    return float((Y[np.arange(len(pred)), pred] == 1).mean())


def fit_and_eval(name, X_all, boards, Y, train_idx, test_idx):
    from sklearn.linear_model import RidgeCV

    Xs, mu, sd = standardize(X_all[train_idx])
    Xs_test = (X_all[test_idx] - mu) / sd

    ridge = RidgeCV(alphas=ALPHAS, cv=5)
    ridge.fit(Xs, Y[train_idx])

    logits_train = Xs @ ridge.coef_.T + ridge.intercept_
    logits_test = Xs_test @ ridge.coef_.T + ridge.intercept_
    train_rate = optimal_move_rate(logits_train, boards[train_idx], Y[train_idx])
    test_rate = optimal_move_rate(logits_test, boards[test_idx], Y[test_idx])
    print(f"[fit] variant {name}: F={X_all.shape[1]:5d}  alpha={ridge.alpha_:10.4g}  "
          f"train_rate={train_rate:.4f}  heldout_rate={test_rate:.4f}")
    return dict(name=name, ridge=ridge, mu=mu, sd=sd, train_rate=train_rate, test_rate=test_rate)


# ---------------------------------------------------------------------------
# Step 4: play evaluation
# ---------------------------------------------------------------------------
def play_eval(pool):
    configs = (
        [("random", game.O)] * N_GAMES_RANDOM
        + [("random", game.X)] * N_GAMES_RANDOM
        + [("minimax", game.O)] * N_GAMES_MINIMAX
        + [("minimax", game.X)] * N_GAMES_MINIMAX
    )
    tasks = [
        (i, opp, side, PLAY_SEED + i) for i, (opp, side) in enumerate(configs)
    ]
    t0 = time.perf_counter()
    results = list(pool.imap_unordered(_play_task, tasks, chunksize=2))
    elapsed = time.perf_counter() - t0

    tally = {}
    for opponent, fly_side, winner in results:
        key = (opponent, fly_side)
        w, d, l = tally.get(key, (0, 0, 0))
        if winner == 0:
            d += 1
        elif winner == fly_side:
            w += 1
        else:
            l += 1
        tally[key] = (w, d, l)

    print(f"\n[play] {len(tasks)} games in {elapsed:.1f}s")
    print(f"{'opponent':<10}{'fly as':<8}{'W':>5}{'D':>5}{'L':>5}")
    for (opponent, fly_side), (w, d, l) in sorted(tally.items()):
        side_name = "X" if fly_side == game.X else "O"
        print(f"{opponent:<10}{side_name:<8}{w:>5}{d:>5}{l:>5}")
    return tally


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true", help="force feature regeneration")
    ap.add_argument("--workers", type=int, default=N_WORKERS)
    args = ap.parse_args()

    t_start = time.perf_counter()
    io = load_io(IO_PATH)

    from multiprocessing import Pool

    with Pool(
        processes=args.workers,
        initializer=_init_worker,
        initargs=(GRAPH_PATH, IO_PATH, config.GAIN, config.DT),
    ) as pool:
        boards, counts_ro, counts_wide, wide_idx = generate_features(pool, io, args.regen)

        # --- Step 2: fit + evaluate A/B/C ---
        # Q-value targets: minimax value of each legal move for the mover
        # (+1 win, 0 draw, -1 loss), illegal cells = -1. Held-out optimal-move
        # rate 0.836 vs 0.805 for multi-hot optimal-move targets on the same features.
        Y = np.array([q_targets(tuple(b)) for b in boards], dtype=np.float32)
        n = boards.shape[0]
        rng = np.random.default_rng(SPLIT_SEED)
        perm = rng.permutation(n)
        n_test = int(round(n * TEST_FRAC))
        test_idx = perm[:n_test]
        train_idx = perm[n_test:]

        X_ro = np.log1p(counts_ro.astype(np.float32))
        X_wide = np.log1p(counts_wide.astype(np.float32))
        X_base = board_onehot(boards)

        print("\n[fit] fitting RidgeCV for variants A (readout), B (wide), C (baseline) ...")
        res_a = fit_and_eval("A (readout,1308)", X_ro, boards, Y, train_idx, test_idx)
        res_b = fit_and_eval("B (wide,4000)", X_wide, boards, Y, train_idx, test_idx)
        res_c = fit_and_eval("C (baseline,27)", X_base, boards, Y, train_idx, test_idx)

        print("\n{:<20}{:>8}{:>12}{:>14}".format("variant", "F", "train_rate", "heldout_rate"))
        for r in (res_a, res_b, res_c):
            print("{:<20}{:>8}{:>12.4f}{:>14.4f}".format(
                r["name"], r["ridge"].coef_.shape[1], r["train_rate"], r["test_rate"]))

        # --- Step 3: pick A vs B, refit on all data, save readout.npz ---
        if (res_b["test_rate"] - res_a["test_rate"]) > PREFER_A_MARGIN:
            chosen = "B"
            X_all, feat_neuron_idx = X_wide, wide_idx
        else:
            chosen = "A"
            X_all, feat_neuron_idx = X_ro, io["readout"]
        print(f"\n[select] chosen variant: {chosen}")

        from sklearn.linear_model import RidgeCV

        Xs_full, mu_full, sd_full = standardize(X_all)
        ridge_final = RidgeCV(alphas=ALPHAS, cv=5)
        ridge_final.fit(Xs_full, Y)
        heldout_rate = res_a["test_rate"] if chosen == "A" else res_b["test_rate"]

        # readout_idx are always RAW neuron indices; the server runs the
        # reservoir with count_idx=readout_idx (see fly/readout.py).
        if chosen == "A":
            readout_idx = io["readout"].astype(np.int32)
        else:
            readout_idx = feat_neuron_idx.astype(np.int32)

        np.savez(
            READOUT_PATH,
            W=ridge_final.coef_.T.astype(np.float32),
            b=ridge_final.intercept_.astype(np.float32),
            mu=mu_full,
            sd=sd_full,
            readout_idx=readout_idx,
            feature=config.FEATURE,
            n_steps=config.N_STEPS,
            dt=config.DT,
            drive=config.DRIVE,
            gain=config.GAIN,
            bias=config.BIAS,
            frame_every=config.FRAME_EVERY,
            alpha=ridge_final.alpha_,
            heldout_rate=heldout_rate,
            variant=chosen,
        )
        print(f"[select] saved {READOUT_PATH} (alpha={ridge_final.alpha_:.4g}, "
              f"heldout_rate={heldout_rate:.4f})")

        # --- Step 4: play evaluation ---
        play_eval(pool)

    print(f"\n[done] total runtime: {time.perf_counter() - t_start:.1f}s")


if __name__ == "__main__":
    main()
