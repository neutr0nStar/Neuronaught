"""Tests for fly.game: tic-tac-toe mechanics and minimax solver."""

import random

import pytest

from fly.game import (
    EMPTY,
    O,
    X,
    is_full,
    is_terminal,
    legal_moves,
    minimax,
    minimax_player,
    optimal_move_targets,
    play,
    play_match,
    random_player,
    reachable_states,
    status,
    to_move,
    training_states,
    winner,
)


def board_from(cells: str):
    """Build a board tuple from a 9-char string, e.g. 'XOX......' """
    mapping = {".": EMPTY, "X": X, "O": O}
    return tuple(mapping[c] for c in cells)


# ---------------------------------------------------------------------------
# winner() detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cells,expected", [
    ("XXX......", X),  # row 0
    ("...XXX...", X),  # row 1
    ("......XXX", X),  # row 2
    ("OOO......", O),  # row 0, O
    ("X..X..X..", X),  # col 0
    (".X..X..X.", X),  # col 1
    ("..X..X..X", X),  # col 2
    ("X...X...X", X),  # diagonal
    ("..X.X.X..", X),  # anti-diagonal
    (".........", 0),  # empty board, no winner
    ("XOXOXOOXO", 0),  # full board, no winner (draw)
])
def test_winner_detection(cells, expected):
    assert winner(board_from(cells)) == expected


# ---------------------------------------------------------------------------
# legal_moves()
# ---------------------------------------------------------------------------

def test_legal_moves_empty_board():
    board = board_from(".........")
    assert legal_moves(board) == list(range(9))


def test_legal_moves_partial_board():
    board = board_from("X.O......")
    assert legal_moves(board) == [1, 3, 4, 5, 6, 7, 8]


def test_legal_moves_terminal_board_is_empty():
    # X has already won; no legal moves remain.
    board = board_from("XXX......")
    assert legal_moves(board) == []
    # Full board (draw) also has no legal moves.
    full = board_from("XOXOXOOXO")
    assert is_full(full)
    assert legal_moves(full) == []


# ---------------------------------------------------------------------------
# to_move()
# ---------------------------------------------------------------------------

def test_to_move_x_first():
    assert to_move(board_from(".........")) == X


def test_to_move_alternates():
    assert to_move(board_from("X........")) == O
    assert to_move(board_from("XO.......")) == X
    assert to_move(board_from("XOX......")) == O


# ---------------------------------------------------------------------------
# play() validation
# ---------------------------------------------------------------------------

def test_play_places_correct_mover():
    board = board_from(".........")
    new_board = play(board, 4)
    assert new_board[4] == X
    new_board2 = play(new_board, 0)
    assert new_board2[0] == O


def test_play_raises_on_occupied_cell():
    board = board_from("X........")
    with pytest.raises(ValueError):
        play(board, 0)


def test_play_raises_on_out_of_range():
    board = board_from(".........")
    with pytest.raises(ValueError):
        play(board, 9)
    with pytest.raises(ValueError):
        play(board, -1)


def test_play_raises_on_terminal_board():
    board = board_from("XXX......")
    with pytest.raises(ValueError):
        play(board, 4)


# ---------------------------------------------------------------------------
# is_terminal / is_full / status
# ---------------------------------------------------------------------------

def test_is_terminal_and_status():
    assert is_terminal(board_from("XXX......"))
    assert status(board_from("XXX......")) == "x_wins"
    assert status(board_from("OOO...XX.")) == "o_wins"
    assert status(board_from("XOXOXOOXO")) == "draw"
    assert status(board_from(".........")) == "x_to_move"
    assert status(board_from("X........")) == "o_to_move"
    assert not is_terminal(board_from("........."))


# ---------------------------------------------------------------------------
# reachable_states() / training_states()
# ---------------------------------------------------------------------------

def test_reachable_states_count():
    states = reachable_states()
    assert len(states) == len(set(states))  # all distinct
    assert len(states) == 5478


def test_training_states_count():
    states = training_states()
    assert all(not is_terminal(b) for b in states)
    assert len(states) == 4520


# ---------------------------------------------------------------------------
# minimax()
# ---------------------------------------------------------------------------

def test_minimax_empty_board_is_a_draw_with_all_moves_optimal():
    value, moves = minimax(board_from("........."))
    # Under perfect play tic-tac-toe is a draw, and symmetry means every
    # opening move is equally optimal (all lead to a draw with correct
    # follow-up play).
    assert value == 0
    assert len(moves) == 9


def test_minimax_forced_win():
    # X: 0, 1 ; O: 3, 4 ; equal piece counts -> X to move, and X can win
    # immediately by playing cell 2 (completes the top row).
    board = board_from("XX.OO....")
    assert to_move(board) == X
    value, moves = minimax(board)
    assert value == 1
    assert 2 in moves


def test_minimax_terminal_value_is_loss_for_player_to_move():
    # Board where X has already won; "to move" would be O, who has lost.
    board = board_from("XXX...OO.")
    value, moves = minimax(board)
    assert value == -1
    assert moves == frozenset()


def test_optimal_move_targets_matches_minimax():
    board = board_from("XX.OO....")
    targets = optimal_move_targets(board)
    assert len(targets) == 9
    assert targets[2] == 1.0
    assert sum(targets) == 1.0  # only cell 2 is optimal here


# ---------------------------------------------------------------------------
# Simulated matches: minimax_player should never lose.
# ---------------------------------------------------------------------------

def test_minimax_player_never_loses_as_x_or_o():
    rng = random.Random(1234)
    x_losses = 0
    o_losses = 0
    for _ in range(300):
        # minimax plays X, random plays O
        result = play_match(minimax_player, random_player, rng)
        if result == O:
            x_losses += 1
        # minimax plays O, random plays X
        result = play_match(random_player, minimax_player, rng)
        if result == X:
            o_losses += 1
    assert x_losses == 0
    assert o_losses == 0
