#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from datetime import datetime


def iso(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_args():
    ap = argparse.ArgumentParser("Summarize end-to-end (wrapper) metrics")
    ap.add_argument("--e2e", required=True, help="Path to e2e JSONL produced by measure_subprocess.py")
    return ap.parse_args()


def main():
    a = parse_args()
    p = Path(a.e2e)
    if not p.exists():
        print(f"e2e metrics not found: {p}")
        return 2

    steps = {}
    first = None
    last = None
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            t = iso(ev.get("ts"))
            if t:
                first = t if first is None else min(first, t)
                last = t if last is None else max(last, t)
            name = ev.get("name")
            if not name:
                continue
            d = steps.setdefault(name, {"wall": 0.0, "cpu": 0.0, "rss": 0, "bytes": 0, "n": 0})
            if ev.get("event") == "step_end":
                d["wall"] += float(ev.get("wall_s") or 0.0)
                d["cpu"] = max(d["cpu"], float(ev.get("cpu_total_s_approx") or 0.0))
                d["rss"] = max(d["rss"], int(ev.get("rss_bytes_max_sum") or 0))
                d["bytes"] += int(ev.get("bytes_delta") or 0)
                d["n"] += 1

    print("=== TESSERA E2E Summary ===")
    if first and last:
        wall_fl = (last-first).total_seconds()
        print(f"End-to-end wall: {wall_fl/3600.0:.2f} h (first→last record)")
    # Also report the sum of step walls (excludes idle gaps between steps)
    step_wall_sum = sum(v["wall"] for v in steps.values())
    print(f"Combined step wall (sum of steps): {step_wall_sum/3600.0:.2f} h")
    total_cpu = sum(v["cpu"] for v in steps.values())
    print(f"Aggregate CPU (approx proc-tree): {total_cpu/3600.0:.2f} h")
    max_rss = max([v["rss"] for v in steps.values()] + [0])
    print(f"Max RSS observed across steps: {max_rss/(1024**3):.2f} GiB")
    total_bytes = sum(v["bytes"] for v in steps.values())
    print(f"Bytes written delta (tracked roots): {total_bytes/(1024**3):.2f} GiB")
    print("")
    for k, v in steps.items():
        print(f"Step {k}: wall {v['wall']/3600.0:.2f} h | cpu {v['cpu']/3600.0:.2f} h | maxRSS {v['rss']/(1024**3):.2f} GiB | bytes {v['bytes']/(1024**3):.2f} GiB (n={v['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
