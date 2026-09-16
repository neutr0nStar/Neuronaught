"""Pick the input (visual board) and readout (descending neuron) groups for the
tic-tac-toe reservoir, from the neuron index built by 01_build_graph.py.

Reads:
    data/processed/neurons.npz

Writes:
    data/processed/io_groups.npz
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROCESSED = os.path.join(HERE, "..", "data", "processed")

ON_TYPES = {"L1", "Mi1", "Tm3", "L3"}
OFF_TYPES = {"L2", "Tm1", "Tm2", "L5"}
CAP = 150
SEED = 0
MIN_HEX_FOR_R = 10_000
COL_MARGIN = 0.10  # fraction of the outer column margin to drop (total, both sides)


def tertile_bins(values):
    """Equal-count tertile assignment (0, 1, 2) robust to ties."""
    order = np.argsort(values, kind="stable")
    bins = np.zeros(len(values), dtype=np.int64)
    for i, part in enumerate(np.array_split(order, 3)):
        bins[part] = i
    return bins


def main():
    d = np.load(os.path.join(PROCESSED, "neurons.npz"), allow_pickle=False)
    superclass = d["superclass"]
    superclass_names = d["superclass_names"]
    side = d["side"]
    type_arr = d["type"]
    hex1 = d["hex1"]
    hex2 = d["hex2"]

    ol_code = int(np.nonzero(superclass_names == "ol_intrinsic")[0][0])
    is_ol = superclass == ol_code
    has_hex = ~np.isnan(hex1) & ~np.isnan(hex2)

    r_count = int((is_ol & has_hex & (side == 1)).sum())
    l_count = int((is_ol & has_hex & (side == 0)).sum())
    print(f"[io] hex-tagged ol_intrinsic neurons: R={r_count} L={l_count}")

    if r_count >= MIN_HEX_FOR_R:
        chosen_side, chosen_name = 1, "R"
    elif r_count >= l_count:
        chosen_side, chosen_name = 1, "R"
    else:
        chosen_side, chosen_name = 0, "L"
    print(f"[io] using side={chosen_name} ({chosen_side})")

    mask = is_ol & has_hex & (side == chosen_side)
    idx = np.nonzero(mask)[0]
    h1 = hex1[idx].astype(np.float64)
    h2 = hex2[idx].astype(np.float64)
    print(f"[io] hex-tagged neurons on chosen side: {len(idx)}")

    # Drop outer column margin (based on hex2) before splitting into tertiles.
    lo, hi = np.percentile(h2, [100 * COL_MARGIN / 2, 100 * (1 - COL_MARGIN / 2)])
    keep = (h2 >= lo) & (h2 <= hi)
    idx = idx[keep]
    h1 = h1[keep]
    h2 = h2[keep]
    print(f"[io] after dropping outer {COL_MARGIN * 100:.0f}% column margin: {len(idx)}")

    row_bin = tertile_bins(h1)
    col_bin = tertile_bins(h2)
    cell = row_bin * 3 + col_bin

    types = type_arr[idx]
    rng = np.random.default_rng(SEED)

    input_X = np.full((9, CAP), -1, dtype=np.int32)
    input_O = np.full((9, CAP), -1, dtype=np.int32)
    input_X_len = np.zeros(9, dtype=np.int32)
    input_O_len = np.zeros(9, dtype=np.int32)

    summary_rows = []
    for c in range(9):
        cell_idx = idx[cell == c]
        cell_types = types[cell == c]

        x_idx = cell_idx[np.isin(cell_types, list(ON_TYPES))]
        o_idx = cell_idx[np.isin(cell_types, list(OFF_TYPES))]

        x_full, o_full = len(x_idx), len(o_idx)
        if len(x_idx) > CAP:
            x_idx = rng.choice(x_idx, size=CAP, replace=False)
        if len(o_idx) > CAP:
            o_idx = rng.choice(o_idx, size=CAP, replace=False)

        input_X[c, : len(x_idx)] = x_idx
        input_O[c, : len(o_idx)] = o_idx
        input_X_len[c] = len(x_idx)
        input_O_len[c] = len(o_idx)
        summary_rows.append((c, x_full, len(x_idx), o_full, len(o_idx)))

    dn_code = int(np.nonzero(superclass_names == "descending_neuron")[0][0])
    readout = np.nonzero(superclass == dn_code)[0].astype(np.int32)
    readout_names = type_arr[readout]
    print(f"[io] readout (descending_neuron) size: {len(readout)}")

    np.savez(
        os.path.join(PROCESSED, "io_groups.npz"),
        input_X=input_X,
        input_X_len=input_X_len,
        input_O=input_O,
        input_O_len=input_O_len,
        readout=readout,
        readout_names=readout_names,
    )

    print("[io] summary (cell: X_available/X_used  O_available/O_used):")
    for c, xf, xu, of, ou in summary_rows:
        print(f"  cell {c} (row={c // 3}, col={c % 3}): X {xf}/{xu}   O {of}/{ou}")
    print(f"[io] readout size: {len(readout)}")


if __name__ == "__main__":
    main()
