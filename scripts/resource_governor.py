#!/usr/bin/env python3
import os
import re
import shutil
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, wait
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NETWORK_PRESSURE_RE = re.compile(
    r"(?:HTTP Error (?:403|408|429|503)|\b(?:403|408|429|503)\b|timed? out|timeout|"
    r"WinError 10060|connection reset|temporarily unavailable|too many requests)",
    re.I,
)


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


def memory_percent():
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
        total = values["MemTotal"]
        available = values.get("MemAvailable", values.get("MemFree", 0))
    except (OSError, ValueError, KeyError):
        return None, None
    used_percent = round(max(0, total - available) / total * 100, 1) if total else None
    return used_percent, available


class ResourceLimitExceeded(RuntimeError):
    pass


class AdaptiveResourceGovernor:
    """Keep collection busy while preserving headroom for the web service."""

    def __init__(
        self,
        target_cpu_percent=80,
        max_memory_percent=80,
        max_disk_percent=85,
        min_free_memory_gb=4,
        sample_seconds=0.5,
        history_size=60,
    ):
        self.target_cpu_percent = float(target_cpu_percent)
        self.max_memory_percent = float(max_memory_percent)
        self.max_disk_percent = float(max_disk_percent)
        self.min_free_memory_bytes = int(float(min_free_memory_gb) * 1024**3)
        self.sample_seconds = max(0.05, float(sample_seconds))
        self.previous_cpu = read_cpu_totals()
        self.last_sample_at = 0.0
        self.snapshot = {
            "cpuPercent": None,
            "memoryPercent": None,
            "freeMemoryBytes": None,
            "diskPercent": None,
            "networkPressurePercent": 0.0,
            "throttled": False,
            "reason": "",
        }
        self.outcomes = deque(maxlen=max(20, int(history_size)))

    @classmethod
    def from_env(cls):
        return cls(
            target_cpu_percent=os.environ.get("WHEREISKELLEY_TARGET_CPU_PERCENT", "80"),
            max_memory_percent=os.environ.get("WHEREISKELLEY_MAX_MEMORY_PERCENT", "80"),
            max_disk_percent=os.environ.get("WHEREISKELLEY_MAX_DISK_PERCENT", "85"),
            min_free_memory_gb=os.environ.get("WHEREISKELLEY_MIN_FREE_MEMORY_GB", "4"),
            sample_seconds=os.environ.get("WHEREISKELLEY_RESOURCE_GOVERNOR_SAMPLE_SECONDS", "0.5"),
        )

    def sample(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_sample_at < self.sample_seconds:
            return self.snapshot
        current_cpu = read_cpu_totals()
        measured_cpu = cpu_percent(self.previous_cpu, current_cpu)
        if current_cpu:
            self.previous_cpu = current_cpu
        measured_memory, free_memory = memory_percent()
        disk_total, disk_used, _disk_free = shutil.disk_usage(ROOT)
        pressure = self.network_pressure_percent()
        self.snapshot.update(
            cpuPercent=measured_cpu,
            memoryPercent=measured_memory,
            freeMemoryBytes=free_memory,
            diskPercent=round(disk_used / disk_total * 100, 1) if disk_total else None,
            networkPressurePercent=pressure,
        )
        self.last_sample_at = now
        return self.snapshot

    def report(self, error=""):
        self.outcomes.append(bool(error and NETWORK_PRESSURE_RE.search(str(error))))
        self.snapshot["networkPressurePercent"] = self.network_pressure_percent()

    def network_pressure_percent(self):
        if len(self.outcomes) < 20:
            return 0.0
        return round(sum(self.outcomes) / len(self.outcomes) * 100, 1)

    def pending_limit(self, workers):
        workers = max(1, int(workers))
        snapshot = self.sample()
        cpu = snapshot.get("cpuPercent")
        memory = snapshot.get("memoryPercent")
        pressure = snapshot.get("networkPressurePercent") or 0
        limit = workers * 2
        reason = ""
        if pressure >= 25:
            limit = max(1, workers // 2)
            reason = "remote sites are throttling or timing out"
        elif pressure >= 12:
            limit = max(1, int(workers * 0.75))
            reason = "remote-site errors are elevated"
        if memory is not None and memory >= self.max_memory_percent:
            limit = 1
            reason = "memory reached its safety limit"
        elif cpu is not None and cpu >= self.target_cpu_percent + 8:
            limit = min(limit, max(1, int(workers * 0.75)))
            reason = "CPU is above the target range"
        elif cpu is not None and cpu >= self.target_cpu_percent:
            limit = min(limit, max(1, int(workers * 0.9)))
            reason = "CPU is at the target range"
        self.snapshot["throttled"] = bool(reason)
        self.snapshot["reason"] = reason
        self.snapshot["pendingLimit"] = limit
        return limit

    def capacity_available(self, force=False):
        snapshot = self.sample(force=force)
        disk = snapshot.get("diskPercent")
        memory = snapshot.get("memoryPercent")
        free_memory = snapshot.get("freeMemoryBytes")
        if disk is not None and disk >= self.max_disk_percent:
            raise ResourceLimitExceeded(
                f"Disk usage reached {disk}% (limit {self.max_disk_percent}%)."
            )
        memory_full = memory is not None and memory >= self.max_memory_percent
        memory_low = free_memory is not None and free_memory < self.min_free_memory_bytes
        if memory_full or memory_low:
            self.snapshot["throttled"] = True
            self.snapshot["reason"] = "waiting for memory headroom"
            return False
        return True

    def wait_for_capacity(self):
        while not self.capacity_available(force=True):
            time.sleep(self.sample_seconds)
        return self.snapshot

    def progress_payload(self, workers):
        snapshot = dict(self.sample())
        snapshot["configuredWorkers"] = int(workers)
        snapshot["pendingLimit"] = self.pending_limit(workers)
        snapshot["targetCpuPercent"] = self.target_cpu_percent
        snapshot["maxMemoryPercent"] = self.max_memory_percent
        snapshot["maxDiskPercent"] = self.max_disk_percent
        return snapshot


def bounded_futures(executor, items, submit, workers, governor):
    """Yield completed futures without queueing the entire collection in memory."""
    iterator = iter(items)
    pending = {}
    exhausted = False
    while pending or not exhausted:
        limit = governor.pending_limit(workers)
        while not exhausted and len(pending) < limit:
            if not governor.capacity_available():
                break
            try:
                item = next(iterator)
            except StopIteration:
                exhausted = True
                break
            future = submit(executor, item)
            pending[future] = item
        if not pending and not exhausted:
            governor.wait_for_capacity()
            continue
        completed, _remaining = wait(pending, return_when=FIRST_COMPLETED)
        for future in completed:
            item = pending.pop(future)
            yield future, item
