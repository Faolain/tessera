#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
from datetime import datetime

def parse_args():
    ap = argparse.ArgumentParser("Summarize TESSERA S2 metrics JSONL")
    ap.add_argument("--metrics", required=True, help="Path to metrics JSONL produced by --metrics_jsonl")
    return ap.parse_args()

def iso(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def main():
    a = parse_args()
    p = Path(a.metrics)
    if not p.exists():
        print(f"Metrics file not found: {p}", file=sys.stderr)
        sys.exit(2)

    run = {"start": None, "end": None, "args": {}, "roi": {}}
    days = []
    scl_pcts = []
    total_bytes = 0
    total_wall = 0.0
    first_ts = None
    last_ts = None
    cpu_total_s = None
    max_rss_seen = 0

    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            ts = iso(ev.get("ts"))
            if ts:
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
            e = ev.get("event")
            if e == "run_start":
                run["start"] = ts
                run["args"] = ev.get("args", {})
                run["roi"] = ev.get("roi", {})
            elif e == "run_end":
                run["end"] = ts
                proc = ev.get("proc") or {}
                cpu_total_s = proc.get("cpu_total_s", cpu_total_s)
                max_rss_seen = max(max_rss_seen, int(proc.get("max_rss_bytes_seen", 0)))
            elif e == "day_end":
                days.append(ev)
                total_bytes += int(ev.get("bytes_written", 0) or 0)
                total_wall += float(ev.get("wall_s", 0.0) or 0.0)
                if ev.get("scl_valid_pct") is not None:
                    try:
                        scl_pcts.append(float(ev.get("scl_valid_pct")))
                    except Exception:
                        pass
            else:
                # harvest max RSS if present
                proc = ev.get("proc") or {}
                max_rss_seen = max(max_rss_seen, int(proc.get("max_rss_bytes_seen", 0)))

    # Fallbacks
    wall_elapsed = None
    if run["start"] and run["end"]:
        wall_elapsed = (run["end"] - run["start"]).total_seconds()
    elif first_ts and last_ts:
        wall_elapsed = (last_ts - first_ts).total_seconds()

    days_success = sum(1 for d in days if d.get("success"))
    days_total = len(days)

    # Throughput estimates
    days_per_hr = None
    if wall_elapsed and wall_elapsed > 0:
        days_per_hr = days_success / (wall_elapsed / 3600.0)

    mib_total = total_bytes / (1024*1024)
    mibps = None
    if total_wall and total_wall > 0:
        mibps = mib_total / total_wall

    # CPU hours
    cpu_hours = (cpu_total_s / 3600.0) if cpu_total_s is not None else None

    # Print summary
    print("=== TESSERA S2 Metrics Summary ===")
    if run["roi"]:
        print(f"ROI: {run['roi'].get('width')}x{run['roi'].get('height')} CRS={run['roi'].get('crs')}")
    if run["args"]:
        print(f"Window: {run['args'].get('start_date')} → {run['args'].get('end_date')}")
        print(f"Workers: {run['args'].get('dask_workers')} mem/worker GB: {run['args'].get('worker_memory_gb')}")
    if wall_elapsed is not None:
        print(f"Wall elapsed: {wall_elapsed/3600.0:.2f} h")
    if cpu_hours is not None:
        print(f"CPU hours (proc-tree): {cpu_hours:.2f} h")
    if max_rss_seen:
        print(f"Max RSS observed: {max_rss_seen/ (1024**3):.2f} GiB")
    print(f"Days processed: {days_success}/{days_total}")
    if days_per_hr is not None:
        print(f"Throughput: {days_per_hr:.2f} days/hr")
    print(f"Bytes written (mosaics): {mib_total/1024:.2f} GiB")
    if mibps is not None:
        print(f"Useful write rate: {mibps:.2f} MiB/s")
    if scl_pcts:
        import numpy as np
        arr = np.array(scl_pcts, dtype=float)
        print(f"SCL valid pct: mean {arr.mean():.2f}% | median {np.median(arr):.2f}% | p10 {np.percentile(arr,10):.2f}% | p90 {np.percentile(arr,90):.2f}%")

if __name__ == "__main__":
    main()

