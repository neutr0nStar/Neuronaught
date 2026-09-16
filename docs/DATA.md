# Data

## Source files

Downloaded by `scripts/00_download.py` from the public GCS bucket
`https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/`
(no auth, ~560 MB total, resumable):

| File | Size | Used for |
|---|---|---|
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 14.5 MB | neuron identity: `bodyId`, `status`, `superclass`, `type`, `somaSide`, `somaLocation`, `assignedOlHex1`, `assignedOlHex2` |
| `body-neurotransmitters-male-cns-v1.0.feather` | 43 MB | per-neuron `consensus_nt` (predicted neurotransmitter), for edge sign |
| `connectome-weights-male-cns-v1.0-minconf-0.5-significant-only.feather` | 502 MB | pre/post body IDs + synapse count per directed pair |

## Neuron set

`scripts/01_build_graph.py` keeps neurons where `status == "Traced"` **and** `somaLocation` is present (a 3-vector) — this is the **140,024**-neuron set used everywhere in this project (soma xyz, for the 3D viewer, and everything downstream). Soma xyz is centered on the mean and scaled by the max absolute coordinate to fit in [-1, 1].

Other columns kept per neuron: `superclass` (factorized to int8 codes, e.g. `ol_intrinsic`, `descending_neuron`; NaN → `"unknown"`), `side` (`L`=0, `R`=1, `M`=2, unknown=3), `type` (cell type string), `hex1`/`hex2` (optic-lobe retinotopic column address, NaN if not applicable).

## Edge construction and thresholds

Rows are kept only if both endpoints (`pre`, `post`) are in the 140,024-neuron set. `scripts/01_build_graph.py` prints edge counts at several synapse-count thresholds before picking one:

| threshold (min synapses) | edges kept |
|---|---|
| ≥ 1 | 23.2 M |
| ≥ 3 | 9.4 M |
| **≥ 5 (chosen)** | **5.54 M** |
| ≥ 10 | 2.41 M |

`EDGE_THRESHOLD = 5` is used for `data/processed/graph.npz` (5,536,352 directed, signed connections). This trades off recall of weak connections against sparsity (and therefore simulation speed).

## Sign convention

Each kept edge's weight is `0.275 mV × synapse_count`, signed by the presynaptic neuron's predicted neurotransmitter (`consensus_nt`):

| Neurotransmitter | Sign |
|---|---|
| acetylcholine, dopamine, octopamine, serotonin | excitatory (+) |
| GABA, glutamate, histamine | inhibitory (−) |
| unclear / missing | + (default) |

Weights are clipped to ±20 mV. Duplicate (pre, post) rows are summed (`sum_duplicates`). The resulting matrix is stored as `W[post, pre]` (CSR: `data`, `indices`, `indptr`, `shape`) in `data/processed/graph.npz`.

## Input selection (the fly's "eye")

`scripts/02_pick_io.py` builds the visual input groups from `ol_intrinsic` (optic-lobe intrinsic) neurons that carry a hex-column address (`hex1`, `hex2`), on whichever side has at least `MIN_HEX_FOR_R = 10,000` hex-tagged neurons (falls back to the larger side otherwise; the right eye is used in practice).

1. Drop the outer 10% column margin (`COL_MARGIN = 0.10`, by `hex2` percentile), to avoid using neurons at the visual periphery.
2. Bin the remaining neurons into a 3×3 grid by equal-count tertiles of `hex1` (row) and `hex2` (column) — `tertile_bins`, robust to ties via a stable sort.
3. Within each of the 9 cells, split neurons by cell type into an **ON group** (drives on "X") and an **OFF group** (drives on "O"):
   - ON types (X): `L1`, `L3`, `Mi1`, `Tm3`
   - OFF types (O): `L2`, `L5`, `Tm1`, `Tm2`
4. Cap each group at `CAP = 150` neurons (random subsample, seed 0) so no cell dominates.

Actual group sizes per board cell (`X_available/X_used`, `O_available/O_used`), from a real run:

| cell | X avail/used | O avail/used |
|---|---|---|
| 0 | 150 / 150 | 150 / 150 |
| 1 | 102 / 102 | 150 / 150 |
| 2 | 39 / 39 | 82 / 82 |
| 3 | 109 / 109 | 150 / 150 |
| 4 | 85 / 85 | 150 / 150 |
| 5 | 133 / 133 | 150 / 150 |
| 6 | 28 / 28 | 53 / 53 |
| 7 | 106 / 106 | 150 / 150 |
| 8 | 150 / 150 | 150 / 150 |

An X drives its cell's ON group at a constant current (`DRIVE = 22 mV`, see `docs/MODEL.md`); an O drives the OFF group; empty cells drive nothing.

## Readout candidates and final features

- All **1,308 descending neurons** (`superclass == descending_neuron`) are saved as `io_groups["readout"]` — the biologically motivated "motor command" population, and one of the two feature sets `scripts/03_train_readout.py` tries.
- The other, better-performing feature set ("wide") is the **4,000** neurons with the highest spike-count variance across a sample of **200 boards**, excluding the input neurons themselves — i.e. the neurons whose activity is most board-sensitive, wherever in the brain they sit. See `docs/RESULTS.md` and `docs/MODEL.md` for how these features are used.

`io_groups.npz` stores `input_X`, `input_X_len`, `input_O`, `input_O_len` (padded [9, 150] int32 arrays + lengths), `readout` (int32 indices), `readout_names`.
