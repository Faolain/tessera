#!/usr/bin/env python3
import argparse, os, sys, time, json, shlex, subprocess, threading
from pathlib import Path
from typing import List, Optional, Dict

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # graceful degrade


def parse_args():
    ap = argparse.ArgumentParser("Run a command and emit step metrics to JSONL")
    ap.add_argument("--jsonl", required=True, help="Path to append JSONL metrics")
    ap.add_argument("--name", required=True, help="Step name (e.g., s2_cpu, s2_stack)")
    ap.add_argument("--bytes-root", default=None, help="Directory whose size delta to report")
    ap.add_argument("--log", default=None, help="Optional path to tee stdout to a log file")
    ap.add_argument("--poll", type=float, default=0.5, help="Polling interval seconds for resource sampling")
    ap.add_argument("--", dest="cmdsep", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run (place after --)")
    return ap.parse_args()


def dir_size_bytes(root: Optional[str]) -> int:
    if not root:
        return 0
    p = Path(root)
    if not p.exists():
        return 0
    total = 0
    for sub in p.rglob("*"):
        try:
            if sub.is_file():
                total += sub.stat().st_size
        except Exception:
            continue
    return total


def proc_tree(p: psutil.Process) -> List[psutil.Process]:  # type: ignore
    procs = [p]
    try:
        procs.extend(p.children(recursive=True))
    except Exception:
        pass
    return procs


def monitor_proc_tree(p: psutil.Process, poll: float, state: Dict[str, float], stop_evt: threading.Event):  # type: ignore
    """Sample proc tree to estimate cpu seconds and track max RSS."""
    cpu_last: Dict[int, float] = {}
    while not stop_evt.is_set():
        try:
            procs = proc_tree(p)
        except Exception:
            break
        rss_sum = 0
        rss_max = 0
        cpu_sum_now = 0.0
        io_r = 0
        io_w = 0
        for q in procs:
            try:
                t = q.cpu_times()
                cpu_sum_now += getattr(t, "user", 0.0) + getattr(t, "system", 0.0)
                m = q.memory_info()
                rss_sum += getattr(m, "rss", 0)
                rss_max = max(rss_max, getattr(m, "rss", 0))
                try:
                    io = q.io_counters()
                    io_r += getattr(io, "read_bytes", 0)
                    io_w += getattr(io, "write_bytes", 0)
                except Exception:
                    pass
            except Exception:
                continue

        # track maxes
        state["rss_bytes_max_sum"] = max(state.get("rss_bytes_max_sum", 0), float(rss_sum))
        state["rss_bytes_max_single"] = max(state.get("rss_bytes_max_single", 0), float(rss_max))
        state["io_read_bytes_max"] = max(state.get("io_read_bytes_max", 0), float(io_r))
        state["io_write_bytes_max"] = max(state.get("io_write_bytes_max", 0), float(io_w))
        # approx cpu seconds across tree: take maximum observed cumulative
        state["cpu_total_s_approx"] = max(state.get("cpu_total_s_approx", 0.0), float(cpu_sum_now))
        stop_evt.wait(poll)


def main():
    a = parse_args()
    if not a.cmd:
        print("Provide command after --", file=sys.stderr)
        return 2

    jsonl = Path(a.jsonl)
    jsonl.parent.mkdir(parents=True, exist_ok=True)

    before_bytes = dir_size_bytes(a.bytes_root)
    start_ts = time.time()
    rec_start = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_ts)),
        "event": "step_start",
        "name": a.name,
        "cmd": " ".join([shlex.quote(x) for x in a.cmd]),
        "bytes_root": a.bytes_root,
    }
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec_start) + "\n")

    log_fp = open(a.log, "a", encoding="utf-8") if a.log else None
    try:
        # run process
        proc = subprocess.Popen(a.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        # monitor thread (only if psutil available)
        state: Dict[str, float] = {}
        stop_evt = threading.Event()
        mon = None
        if psutil is not None:
            try:
                mon = threading.Thread(target=monitor_proc_tree, args=(psutil.Process(proc.pid), a.poll, state, stop_evt), daemon=True)
                mon.start()
            except Exception:
                mon = None

        # stream stdout
        last_lines = []
        if proc.stdout is not None:
            for line in proc.stdout:
                if log_fp:
                    log_fp.write(line)
                # keep short tail buffer for convenience
                last_lines.append(line.rstrip())
                if len(last_lines) > 50:
                    last_lines.pop(0)

        exit_code = proc.wait()
        end_ts = time.time()
        if mon is not None:
            stop_evt.set()
            mon.join(timeout=2)

        after_bytes = dir_size_bytes(a.bytes_root)
        bytes_delta = after_bytes - before_bytes if a.bytes_root else None

        rec_end = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_ts)),
            "event": "step_end",
            "name": a.name,
            "exit_code": exit_code,
            "wall_s": end_ts - start_ts,
            "cpu_total_s_approx": state.get("cpu_total_s_approx"),
            "rss_bytes_max_sum": state.get("rss_bytes_max_sum"),
            "rss_bytes_max_single": state.get("rss_bytes_max_single"),
            "io_read_bytes_max": state.get("io_read_bytes_max"),
            "io_write_bytes_max": state.get("io_write_bytes_max"),
            "bytes_delta": bytes_delta,
            "tail": last_lines,
        }
        with jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec_end) + "\n")

        # Return child exit code
        return exit_code
    finally:
        if log_fp:
            log_fp.flush()
            log_fp.close()


if __name__ == "__main__":
    sys.exit(main())

