"""Download the Male CNS v1.0 flat connectome files needed for the project.

Public GCS bucket, no auth. ~560 MB total. Resumable.
"""
import os
import sys
import urllib.request

BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
FILES = [
    "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "body-neurotransmitters-male-cns-v1.0.feather",
    "connectome-weights-male-cns-v1.0-minconf-0.5-significant-only.feather",
]
RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def remote_size(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req) as r:
        return int(r.headers["Content-Length"])


def download(name):
    url = BASE + name
    dst = os.path.join(RAW, name)
    total = remote_size(url)
    have = os.path.getsize(dst) if os.path.exists(dst) else 0
    if have == total:
        print(f"[skip] {name} ({total/1e6:.1f} MB)")
        return
    req = urllib.request.Request(url)
    if have:
        req.add_header("Range", f"bytes={have}-")
    print(f"[get ] {name} {have/1e6:.1f}/{total/1e6:.1f} MB")
    with urllib.request.urlopen(req) as r, open(dst, "ab") as f:
        while chunk := r.read(1 << 22):
            f.write(chunk)
            have += len(chunk)
            print(f"\r      {have/1e6:8.1f}/{total/1e6:.1f} MB", end="", file=sys.stderr)
    print()
    assert os.path.getsize(dst) == total, f"size mismatch for {name}"


if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    for n in FILES:
        download(n)
    print("done")
