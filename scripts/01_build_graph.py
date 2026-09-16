"""Build the neuron index and weighted connectivity graph for the Male CNS v1.0
flat connectome.

Reads:
    data/raw/body-annotations-male-cns-v1.0-minconf-0.5.feather
    data/raw/body-neurotransmitters-male-cns-v1.0.feather
    data/raw/connectome-weights-male-cns-v1.0-minconf-0.5-significant-only.feather

Writes:
    data/processed/neurons.npz
    data/processed/graph.npz
"""
import os
import time

import numpy as np
import pandas as pd
import pyarrow.feather as feather
import scipy.sparse as sp

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "..", "data", "raw")
PROCESSED = os.path.join(HERE, "..", "data", "processed")

ANNOT = os.path.join(RAW, "body-annotations-male-cns-v1.0-minconf-0.5.feather")
NT = os.path.join(RAW, "body-neurotransmitters-male-cns-v1.0.feather")
WEIGHTS = os.path.join(
    RAW, "connectome-weights-male-cns-v1.0-minconf-0.5-significant-only.feather"
)

EXCITATORY_NT = {"acetylcholine", "dopamine", "octopamine", "serotonin"}
INHIBITORY_NT = {"gaba", "glutamate", "histamine"}

SYN_SCALE = 0.275  # mV per synapse
W_CLIP = 20.0  # mV, symmetric clip
EDGE_THRESHOLD = 5  # min synapse (weight) count to keep an edge


def build_neurons():
    t0 = time.time()
    cols = [
        "bodyId",
        "status",
        "superclass",
        "type",
        "somaSide",
        "somaLocation",
        "assignedOlHex1",
        "assignedOlHex2",
    ]
    df = feather.read_table(ANNOT, columns=cols).to_pandas()

    traced = df[df["status"] == "Traced"].copy()
    has_soma = traced["somaLocation"].apply(
        lambda x: x is not None and len(x) == 3
    )
    neur = traced[has_soma].copy()
    neur = neur.sort_values("bodyId").reset_index(drop=True)
    n = len(neur)
    print(f"[neurons] traced={len(traced)} with_soma={n}")

    body_id = neur["bodyId"].to_numpy(dtype=np.int64)

    # xyz: stack somaLocation, center on mean, scale by 1/max_abs -> fits [-1, 1]
    xyz_raw = np.stack(neur["somaLocation"].to_numpy()).astype(np.float64)
    xyz_centered = xyz_raw - xyz_raw.mean(axis=0, keepdims=True)
    max_abs = np.max(np.abs(xyz_centered))
    xyz = (xyz_centered / max_abs).astype(np.float32)

    # superclass: NaN -> 'unknown', factorize to int8 codes + names
    superclass_filled = neur["superclass"].fillna("unknown").astype(str)
    superclass_codes, superclass_names = pd.factorize(superclass_filled, sort=True)
    superclass_codes = superclass_codes.astype(np.int8)
    superclass_names = np.array(superclass_names, dtype="U")

    # side: L=0, R=1, M=2, unknown=3
    side_map = {"L": 0, "R": 1, "M": 2}
    side = (
        neur["somaSide"]
        .map(side_map)
        .fillna(3)
        .astype(np.int8)
        .to_numpy()
    )

    # type: object strings, NaN -> 'unknown'
    type_arr = neur["type"].fillna("unknown").astype(str).to_numpy(dtype="U")

    hex1 = neur["assignedOlHex1"].to_numpy(dtype=np.float32)
    hex2 = neur["assignedOlHex2"].to_numpy(dtype=np.float32)

    # neurotransmitter sign, joined by bodyId
    nt_df = feather.read_table(NT, columns=["body", "consensus_nt"]).to_pandas()
    nt_map = dict(zip(nt_df["body"].to_numpy(), nt_df["consensus_nt"].to_numpy()))

    def sign_for(nt):
        if nt in EXCITATORY_NT:
            return 1
        if nt in INHIBITORY_NT:
            return -1
        return 1  # unclear/missing -> +1

    nt_sign = np.array(
        [sign_for(nt_map.get(b)) for b in body_id], dtype=np.int8
    )

    np.savez(
        os.path.join(PROCESSED, "neurons.npz"),
        body_id=body_id,
        xyz=xyz,
        superclass=superclass_codes,
        superclass_names=superclass_names,
        side=side,
        type=type_arr,
        hex1=hex1,
        hex2=hex2,
        nt_sign=nt_sign,
    )
    print(f"[neurons] wrote neurons.npz in {time.time() - t0:.1f}s")
    return body_id, nt_sign, neur


def build_graph(body_id, nt_sign, neur):
    t0 = time.time()
    n = len(body_id)
    body_to_idx = {b: i for i, b in enumerate(body_id)}

    schema = feather.read_table(WEIGHTS, columns=None).schema
    print("[weights] schema:")
    print(schema)

    col_names = schema.names
    pre_col = next(c for c in col_names if "pre" in c.lower())
    post_col = next(c for c in col_names if "post" in c.lower())
    weight_col = next(
        c
        for c in col_names
        if c not in (pre_col, post_col)
        and ("weight" in c.lower() or "count" in c.lower() or "syn" in c.lower())
    )
    print(f"[weights] using pre={pre_col!r} post={post_col!r} weight={weight_col!r}")

    wt = feather.read_table(WEIGHTS, columns=[pre_col, post_col, weight_col]).to_pandas()
    wt.columns = ["pre", "post", "count"]
    print(f"[weights] total rows={len(wt)}")

    in_set = wt["pre"].isin(body_to_idx) & wt["post"].isin(body_to_idx)
    wt = wt[in_set]
    print(f"[weights] rows with both endpoints in neuron set: {len(wt)}")

    for thr in (1, 3, 5, 10):
        n_edges = (wt["count"] >= thr).sum()
        print(f"[weights] threshold >= {thr}: {n_edges} edges")

    wt = wt[wt["count"] >= EDGE_THRESHOLD]
    print(f"[weights] chosen threshold >= {EDGE_THRESHOLD}: {len(wt)} edges kept")

    pre_idx = wt["pre"].map(body_to_idx).to_numpy()
    post_idx = wt["post"].map(body_to_idx).to_numpy()
    count = wt["count"].to_numpy(dtype=np.float64)

    signed_weight = nt_sign[pre_idx].astype(np.float64) * SYN_SCALE * count
    signed_weight = np.clip(signed_weight, -W_CLIP, W_CLIP).astype(np.float32)

    # W[post, pre] = signed_weight  ->  row=post, col=pre
    mat = sp.coo_matrix(
        (signed_weight, (post_idx, pre_idx)), shape=(n, n), dtype=np.float32
    )
    mat = mat.tocsr()
    mat.sum_duplicates()

    data = mat.data.astype(np.float32)
    indices = mat.indices.astype(np.int32)
    indptr = mat.indptr.astype(np.int64)

    mem_mb = (data.nbytes + indices.nbytes + indptr.nbytes) / 1e6
    nnz = mat.nnz
    mean_in_degree = nnz / n

    print(f"[graph] N={n} nnz={nnz} memory={mem_mb:.1f} MB mean_in_degree={mean_in_degree:.2f}")

    n_descending = int((neur["superclass"] == "descending_neuron").sum())
    n_hex_ol = int(
        neur[neur["superclass"] == "ol_intrinsic"]
        .dropna(subset=["assignedOlHex1", "assignedOlHex2"])
        .shape[0]
    )
    print(f"[graph] descending_neuron survived: {n_descending}")
    print(f"[graph] hex-tagged ol_intrinsic survived: {n_hex_ol}")

    np.savez(
        os.path.join(PROCESSED, "graph.npz"),
        data=data,
        indices=indices,
        indptr=indptr,
        shape=np.array([n, n], dtype=np.int64),
    )
    print(f"[graph] wrote graph.npz in {time.time() - t0:.1f}s")


def main():
    os.makedirs(PROCESSED, exist_ok=True)
    body_id, nt_sign, neur = build_neurons()
    build_graph(body_id, nt_sign, neur)


if __name__ == "__main__":
    main()
