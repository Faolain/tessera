#!/usr/bin/env python3
import argparse, json, os, sys
from pathlib import Path
import numpy as np


def parse_args():
    ap = argparse.ArgumentParser("Validate shapes/dtypes of S2 stacked NPYs")
    ap.add_argument("--npys", required=True, help="Directory with bands.npy/masks.npy/doys.npy")
    ap.add_argument("--jsonl", required=False, help="Optional JSONL to append a validation event")
    return ap.parse_args()


def main():
    a = parse_args()
    root = Path(a.npys)
    out = {"event": "npy_validate", "dir": str(root)}
    ok = True
    for name in ("bands.npy", "masks.npy", "doys.npy"):
        p = root / name
        if not p.exists():
            out[f"{name}_missing"] = True
            ok = False
            continue
        try:
            arr = np.load(p, mmap_mode="r")
            out[f"{name}_shape"] = tuple(int(x) for x in arr.shape)
            out[f"{name}_dtype"] = str(arr.dtype)
            out[f"{name}_bytes"] = int(arr.size * arr.dtype.itemsize)
        except Exception as e:
            out[f"{name}_error"] = type(e).__name__
            ok = False

    out["ok"] = ok
    msg = json.dumps(out)
    print(msg)
    if a.jsonl:
        try:
            Path(a.jsonl).parent.mkdir(parents=True, exist_ok=True)
            with Path(a.jsonl).open("a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

