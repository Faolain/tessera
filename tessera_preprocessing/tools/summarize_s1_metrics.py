#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
from datetime import datetime

def parse_args():
    ap = argparse.ArgumentParser("Summarize TESSERA S1 metrics JSONL")
    ap.add_argument("--metrics", required=True, help="Path to S1 metrics JSONL produced by --metrics_jsonl")
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
    groups = []
    first_ts = None
    last_ts = None
    cpu_total_s = None
    max_rss_seen = 0
    total_bytes = 0
    total_wall = 0.0

    vv_both = vv_only = vh_only = failed = 0
    items_processed = items_failed = items_skipped = items_no_data = 0

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
                groups.append(ev)
                total_bytes += int(ev.get("bytes_written", 0) or 0)
                total_wall += float(ev.get("wall_s", 0.0) or 0.0)
                vv = bool(ev.get("vv", False))
                vh = bool(ev.get("vh", False))
                if ev.get("success"):
                    if vv and vh:
                        vv_both += 1
                    elif vv and not vh:
                        vv_only += 1
                    elif vh and not vv:
                        vh_only += 1
                else:
                    failed += 1
                items_processed += int(ev.get("items_processed", 0) or 0)
                items_failed += int(ev.get("items_failed", 0) or 0)
                items_skipped += int(ev.get("items_skipped", 0) or 0)
                items_no_data += int(ev.get("items_no_data", 0) or 0)
            else:
                proc = ev.get("proc") or {}
                max_rss_seen = max(max_rss_seen, int(proc.get("max_rss_bytes_seen", 0)))

    wall_elapsed = None
    if run["start"] and run["end"]:
        wall_elapsed = (run["end"] - run["start"]).total_seconds()
    elif first_ts and last_ts:
        wall_elapsed = (last_ts - first_ts).total_seconds()

    groups_total = len(groups)
    groups_success = vv_both + vv_only + vh_only
    groups_per_hr = None
    if wall_elapsed and wall_elapsed > 0:
        groups_per_hr = groups_success / (wall_elapsed / 3600.0)

    gib_total = total_bytes / (1024**3)
    mibps = None
    if total_wall and total_wall > 0:
        mibps = (total_bytes / 1024.0**2) / total_wall

    cpu_hours = (cpu_total_s / 3600.0) if cpu_total_s is not None else None

    print("=== TESSERA S1 Metrics Summary ===")
    if run["roi"]:
        print(f"ROI: {run['roi'].get('width')}x{run['roi'].get('height')} CRS={run['roi'].get('crs')}")
    if run["args"]:
        print(f"Window: {run['args'].get('start_date')} → {run['args'].get('end_date')} | orbit={run['args'].get('orbit_state')}")
        print(f"Workers: {run['args'].get('dask_workers')} mem/worker GB: {run['args'].get('worker_memory_gb')}")
    if wall_elapsed is not None:
        print(f"Wall elapsed: {wall_elapsed/3600.0:.2f} h")
    if cpu_hours is not None:
        print(f"CPU hours (proc-tree): {cpu_hours:.2f} h")
    if max_rss_seen:
        print(f"Max RSS observed: {max_rss_seen/ (1024**3):.2f} GiB")
    print(f"Groups processed (date+orbit): {groups_success}/{groups_total}")
    if groups_per_hr is not None:
        print(f"Throughput: {groups_per_hr:.2f} groups/hr")
    print(f"Bytes written (VV/VH mosaics): {gib_total:.2f} GiB")
    if mibps is not None:
        print(f"Useful write rate: {mibps:.2f} MiB/s")
    print(f"Outcome counts: both {vv_both} | vv-only {vv_only} | vh-only {vh_only} | failed {failed}")
    print(f"Items: processed {items_processed} | skipped {items_skipped} | no_data {items_no_data} | failed {items_failed}")

if __name__ == "__main__":
    main()

