"""Tic-tac-toe game engine.

Board representation: a tuple of 9 ints, row-major (index 0..8):
    0 1 2
    3 4 5
    6 7 8
Cell values: 0 = empty, 1 = X, 2 = O.

This module is pure Python with no external dependencies. It provides
game mechanics (legality, win detection, turn order), an exhaustive
minimax solver (memoized), enumeration of the full reachable state
space, and simple random/optimal players for simulating matches.
"""

from __future__ import annotations

import functools
import random
from typing import Callable

EMPTY, X, O = 0, 1, 2

Board = tuple  # tuple[int, ...] of length 9, kept generic for readability

# All 8 winning lines: 3 rows, 3 cols, 2 diagonals.
_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # cols
    (0, 4, 8), (2, 4, 6),             # diagonals
)


def winner(board) -> int:
    """Return 1 if X has a winning line, 2 if O does, else 0 (no winner)."""
    for a, b, c in _LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return 0


def is_full(board) -> bool:
    """True if there are no empty cells left."""
    return EMPTY not in board


def is_terminal(board) -> bool:
    """True if the game is over: someone has won, or the board is full."""
    return winner(board) != 0 or is_full(board)


def legal_moves(board) -> list:
    """List of empty cell indices. Empty once the board is terminal."""
    if is_terminal(board):
        return []
    return [i for i, v in enumerate(board) if v == EMPTY]


def to_move(board) -> int:
    """Whose turn it is. X always moves first, so X has moved <= O."""
    x_count = board.count(X)
    o_count = board.count(O)
    return X if x_count == o_count else O


def play(board, cell: int):
    """Return a new board with the mover's piece placed at `cell`.

    Raises ValueError if the move is illegal (out of range, occupied,
    or the game is already over).
    """
    if is_terminal(board):
        raise ValueError("cannot play on a terminal board")
    if not (0 <= cell < 9):
        raise ValueError(f"cell {cell} out of range 0..8")
    if board[cell] != EMPTY:
        raise ValueError(f"cell {cell} is already occupied")
    mover = to_move(board)
    new_board = list(board)
    new_board[cell] = mover
    return tuple(new_board)


@functools.lru_cache(maxsize=None)
def minimax(board):
    """Exhaustive minimax search, memoized.

    Returns (value, moves): `value` is from the perspective of the
    player to move on `board` (+1 = that player can force a win,
    0 = best play leads to a draw, -1 = that player is losing under
    best play). `moves` is the frozenset of ALL cells that achieve
    that optimal value (empty frozenset on terminal boards).
    """
    w = winner(board)
    if w != 0 or is_full(board):
        # Terminal board: value is from the perspective of the player
        # "to move" here, i.e. the player who did NOT just move (since
        # the previous player just won or the board filled up). If the
        # previous player won, the player to move has lost: -1.
        if w != 0:
            return (-1, frozenset())
        return (0, frozenset())

    best_value = None
    best_moves = []
    for move in legal_moves(board):
        child = play(board, move)
        child_value, _ = minimax(child)
        # The child's value is from the opponent's perspective, so our
        # value for playing `move` is the negation of that.
        value = -child_value
        if best_value is None or value > best_value:
            best_value = value
            best_moves = [move]
        elif value == best_value:
            best_moves.append(move)
    return (best_value, frozenset(best_moves))


def reachable_states() -> list:
    """All boards reachable from the empty board via legal play (BFS).

    Expansion stops at terminal boards (their children are not
    generated, since no further moves are legal there). Includes the
    empty board itself. Yields exactly 5478 distinct boards.
    """
    start = tuple([EMPTY] * 9)
    seen = {start}
    frontier = [start]
    while frontier:
        next_frontier = []
        for board in frontier:
            if is_terminal(board):
                continue
            for move in legal_moves(board):
                child = play(board, move)
                if child not in seen:
                    seen.add(child)
                    next_frontier.append(child)
        frontier = next_frontier
    return list(seen)


def training_states() -> list:
    """Non-terminal states among all reachable states (4520 of them)."""
    return [b for b in reachable_states() if not is_terminal(b)]


def optimal_move_targets(board) -> list:
    """Length-9 multi-hot vector: 1.0 for each optimal move, else 0.0."""
    _, moves = minimax(board)
    return [1.0 if i in moves else 0.0 for i in range(9)]


def status(board) -> str:
    """Human-readable board status."""
    w = winner(board)
    if w == X:
        return "x_wins"
    if w == O:
        return "o_wins"
    if is_full(board):
        return "draw"
    return "x_to_move" if to_move(board) == X else "o_to_move"


def random_player(board, rng: random.Random) -> int:
    """Pick a uniformly random legal move."""
    return rng.choice(legal_moves(board))


def minimax_player(board, rng: random.Random) -> int:
    """Pick a uniformly random move among the optimal ones."""
    _, moves = minimax(board)
    return rng.choice(sorted(moves))


def play_match(player_x: Callable, player_o: Callable, rng: random.Random) -> int:
    """Play a full game between two (board, rng) -> cell callables.

    Returns the winner (0 for draw, 1 for X, 2 for O).
    """
    board = tuple([EMPTY] * 9)
    while not is_terminal(board):
        mover = to_move(board)
        move = player_x(board, rng) if mover == X else player_o(board, rng)
        board = play(board, move)
    return winner(board)
