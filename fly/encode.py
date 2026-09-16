"""Encode a tic-tac-toe board into external drive current for the reservoir.

io_groups.npz (produced by scripts/02_pick_io.py) gives, for each of the
9 board cells, a group of "X-input" neurons and a group of "O-input"
neurons, padded to a common width K with -1. This module unpads those
into ragged lists of index arrays and builds the per-step ``i_ext``
vector: driven input neurons get a constant current, everyone else 0.

Default drive derivation (see spec): with tau_mem=20ms, v_rest=-52mV,
v_thresh=-45mV, an isolated neuron driven by constant ``i_ext`` and no
recurrent input reaches a steady state v_ss = v_rest + i_ext (from
dv/dt = (v_rest - v + i_ext)/tau_mem = 0). For it to ever reach
threshold at all we need i_ext > v_thresh - v_rest = 7 mV. Solving the
sub-threshold trajectory v(t) = v_rest + i_ext*(1 - exp(-t/tau_mem)) for
the time to cross threshold from reset:

    t_thresh = -tau_mem * ln(1 - 7/i_ext)

For a target firing rate of 100 Hz (period 10 ms), accounting for the
2.2 ms refractory period, the sub-threshold charging time budget is
10 - 2.2 = 7.8 ms, so:

    7.8 = -20 * ln(1 - 7/i_ext)  =>  i_ext = 7 / (1 - exp(-7.8/20)) ~= 21.7 mV

We round up to 22.0 mV as the default drive.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# See module docstring for derivation.
DEFAULT_DRIVE = 22.0


def _unpad_groups(arr: np.ndarray, lens: np.ndarray) -> list[np.ndarray]:
    """Unpad a [G, K] int32 array (padded with -1) into a list of G
    variable-length int arrays, using the parallel ``lens`` array."""
    return [arr[i, : int(lens[i])].astype(np.int64) for i in range(arr.shape[0])]


def load_io(path) -> dict:
    """Load io_groups.npz into unpadded index lists.

    Returns a dict with:
      - "input_X": list of 9 int64 arrays (indices into the N neurons)
      - "input_O": list of 9 int64 arrays
      - "readout": int64 array of readout (descending) neuron indices
      - "readout_names": array of names parallel to "readout"
    """
    with np.load(path, allow_pickle=True) as d:
        input_x = _unpad_groups(d["input_X"], d["input_X_len"])
        input_o = _unpad_groups(d["input_O"], d["input_O_len"])
        readout = d["readout"].astype(np.int64)
        readout_names = d["readout_names"]
    return {
        "input_X": input_x,
        "input_O": input_o,
        "readout": readout,
        "readout_names": readout_names,
    }


def board_to_input(
    board,
    io: dict,
    n: int,
    drive: float = DEFAULT_DRIVE,
    always_on: Optional[np.ndarray] = None,
    bias_drive: float = 0.0,
) -> np.ndarray:
    """Build the float32[n] external-current vector for a board state.

    ``board`` is a length-9 sequence of {0 (empty), 1 (X), 2 (O)}.
    For each cell with an X, the corresponding "input_X" neuron group
    is driven at ``drive`` mV; for O, "input_O". Empty cells drive
    nothing. Optionally, an ``always_on`` index array (e.g. a fixed
    "go" / context group) is driven at ``bias_drive`` mV regardless of
    the board, to avoid a literally all-zero input on the empty board;
    this is off by default (bias_drive=0.0) since the empty board is a
    legal query and the fly is not required to distinguish "no input
    yet" from "empty board" on its own.
    """
    i_ext = np.zeros(n, dtype=np.float32)
    if len(board) != 9:
        raise ValueError(f"board must have 9 cells, got {len(board)}")

    for c, val in enumerate(board):
        if val == 1:
            idx = io["input_X"][c]
        elif val == 2:
            idx = io["input_O"][c]
        else:
            continue
        if idx.size:
            i_ext[idx] = drive

    if always_on is not None and bias_drive:
        always_on = np.asarray(always_on)
        i_ext[always_on] = np.maximum(i_ext[always_on], np.float32(bias_drive))

    return i_ext
