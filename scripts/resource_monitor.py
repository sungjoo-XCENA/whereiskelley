#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "public" / "data" / "resource-history.json"
PROGRESS_PATH = ROOT / "public" / "data" / "guide-progress.json"
DEFAULT_INTERVAL = max(5, int(os.environ.get("WHEREISKELLEY_RESOURCE_SAMPLE_SECONDS", "30")))
MAX_SAMPLES = max(120, int(os.environ.get("WHEREISKELLEY_RESOURCE_MAX_SAMPLES", "1440")))


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def read_cpu_totals():
    try:
        fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
        values = [int(value) for value in fields]
    except (OSError, ValueError, IndexError):
        return None
    total = sum(values)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return total, idle


def cpu_percent(previous, current):
    if not previous or not current:
        return None
    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 1)


def memory_usage():
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
        total = values["MemTotal"]
        available = values.get("MemAvailable", values.get("MemFree", 0))
        used = max(0, total - available)
        return total, used
    except (OSError, ValueError, KeyError):
        return 0, 0


def process_usage(pid):
    if not pid:
        return None, 0
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        stat = stat_text[stat_text.rfind(")") + 2 :].split()
        # Include CPU from children that this process has already reaped.
        ticks = sum(int(stat[index]) for index in (11, 12, 13, 14))
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines()
        rss_kb = next(int(line.split()[1]) for line in status if line.startswith("VmRSS:"))
        return ticks, rss_kb * 1024
    except (OSError, ValueError, StopIteration, IndexError):
        return None, 0


def process_children(pid):
    try:
        value = Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="utf-8").strip()
        return [int(child) for child in value.split()] if value else []
    except (OSError, ValueError):
        return []


def process_tree_usage(pid):
    """Return cumulative CPU ticks and RSS for a process and its live descendants."""
    pending = [pid] if pid else []
    visited = set()
    total_ticks = 0
    total_rss = 0
    found = False
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        ticks, rss = process_usage(current)
        if ticks is not None:
            total_ticks += ticks
            total_rss += rss
            found = True
        pending.extend(process_children(current))
    return (total_ticks if found else None), total_rss


def process_cpu_percent(previous, current, elapsed_seconds, cores):
    if previous is None or current is None or elapsed_seconds <= 0:
        return None
    clock_ticks = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
    used_seconds = max(0, current - previous) / max(1, clock_ticks)
    return round(max(0.0, min(100.0, used_seconds / elapsed_seconds / max(1, cores) * 100)), 1)


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def append_sample(path, sample, progress, interval_seconds):
    run_id = progress.get("runId")
    started_at = progress.get("startedAt") or ""
    history = read_json(path, {})
    if history.get("runId") != run_id or history.get("startedAt") != started_at:
        history = {
            "runId": run_id,
            "startedAt": started_at,
            "intervalSeconds": interval_seconds,
            "samples": [],
        }
    samples = history.setdefault("samples", [])
    samples.append(sample)
    history["generatedAt"] = sample["at"]
    history["intervalSeconds"] = interval_seconds
    history["samples"] = samples[-MAX_SAMPLES:]
    atomic_write_json(path, history)


def monitor_process(process, history_path=HISTORY_PATH, progress_path=PROGRESS_PATH, interval_seconds=DEFAULT_INTERVAL):
    pid = process.pid
    cores = max(1, os.cpu_count() or 1)
    previous_cpu = read_cpu_totals()
    previous_process_ticks, _rss = process_tree_usage(pid)
    previous_at = time.monotonic()

    while True:
        return_code = process.poll()
        now_monotonic = time.monotonic()
        current_cpu = read_cpu_totals()
        current_process_ticks, process_rss = process_tree_usage(pid)
        memory_total, memory_used = memory_usage()
        disk_total, disk_used, disk_free = shutil.disk_usage(ROOT)
        elapsed = max(0.001, now_monotonic - previous_at)
        progress = read_json(progress_path, {})
        try:
            load_1m = round(os.getloadavg()[0], 2)
        except (AttributeError, OSError):
            load_1m = None
        sample = {
            "at": utc_now(),
            "phase": progress.get("phase") or "",
            "phaseProcessed": progress.get("phaseProcessed"),
            "phaseTotal": progress.get("phaseTotal"),
            "sourceCandidatesProcessed": progress.get("sourceCandidatesProcessed"),
            "sourceCandidatesTotal": progress.get("sourceCandidatesTotal"),
            "restaurantsFinalized": progress.get("processedTargets"),
            "restaurantsTotal": progress.get("totalWebsites"),
            "cpuPercent": cpu_percent(previous_cpu, current_cpu),
            "collectorCpuPercent": process_cpu_percent(
                previous_process_ticks, current_process_ticks, elapsed, cores
            ),
            "memoryPercent": round(memory_used / memory_total * 100, 1) if memory_total else None,
            "memoryUsedBytes": memory_used,
            "memoryTotalBytes": memory_total,
            "collectorMemoryBytes": process_rss,
            "diskPercent": round(disk_used / disk_total * 100, 1) if disk_total else None,
            "diskUsedBytes": disk_used,
            "diskFreeBytes": disk_free,
            "diskTotalBytes": disk_total,
            "load1m": load_1m,
            "cores": cores,
        }
        append_sample(history_path, sample, progress, interval_seconds)
        previous_cpu = current_cpu
        previous_process_ticks = current_process_ticks
        previous_at = now_monotonic
        if return_code is not None:
            history = read_json(history_path, {})
            history["finishedAt"] = sample["at"]
            history["exitCode"] = return_code
            atomic_write_json(history_path, history)
            return return_code
        time.sleep(interval_seconds)


class ProcessHandle:
    def __init__(self, pid):
        self.pid = pid

    def poll(self):
        try:
            os.kill(self.pid, 0)
            return None
        except ProcessLookupError:
            return 0
        except PermissionError:
            return None


def main():
    parser = argparse.ArgumentParser(description="Record server resource usage while a collection process runs.")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--history", type=Path, default=HISTORY_PATH)
    parser.add_argument("--progress", type=Path, default=PROGRESS_PATH)
    args = parser.parse_args()
    return monitor_process(
        ProcessHandle(args.pid),
        history_path=args.history,
        progress_path=args.progress,
        interval_seconds=max(5, args.interval),
    )


if __name__ == "__main__":
    raise SystemExit(main())
