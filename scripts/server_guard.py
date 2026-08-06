#!/usr/bin/env python3
import json
import os
import signal
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "public" / "data" / "server-guard.json"
WATCH_PATH = Path(os.environ.get("WHEREISKELLEY_GUARD_PATH", str(ROOT)))

WARN_PCT = float(os.environ.get("WHEREISKELLEY_GUARD_WARN_PCT", "75"))
STOP_COLLECTION_PCT = float(os.environ.get("WHEREISKELLEY_GUARD_STOP_COLLECTION_PCT", "85"))
CLOSE_WEB_PCT = float(os.environ.get("WHEREISKELLEY_GUARD_CLOSE_WEB_PCT", "92"))
REOPEN_WEB_PCT = float(os.environ.get("WHEREISKELLEY_GUARD_REOPEN_WEB_PCT", "80"))


def run(args):
    return subprocess.run(args, text=True, capture_output=True, check=False)


def nginx_active():
    return run(["systemctl", "is-active", "nginx"]).stdout.strip() == "active"


def stop_nginx(actions):
    if nginx_active():
        result = run(["systemctl", "stop", "nginx"])
        actions.append({
            "action": "stop_nginx",
            "ok": result.returncode == 0,
            "detail": (result.stderr or result.stdout).strip(),
        })


def start_nginx(actions):
    if not nginx_active():
        result = run(["systemctl", "start", "nginx"])
        actions.append({
            "action": "start_nginx",
            "ok": result.returncode == 0,
            "detail": (result.stderr or result.stdout).strip(),
        })


def collector_processes():
    result = run(["ps", "-eo", "pid=,args="])
    processes = []
    own_pid = os.getpid()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_text, _, args = line.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == own_pid:
            continue
        if "/scripts/guide_" not in args:
            continue
        if not any(token in args for token in ("guide_collect", "guide_discover", "guide_audit")):
            continue
        processes.append({"pid": pid, "cmd": args})
    return processes


def stop_collectors(actions):
    stopped = []
    for process in collector_processes():
        try:
            os.kill(process["pid"], signal.SIGTERM)
            stopped.append(process)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            actions.append({"action": "stop_collector", "ok": False, "detail": str(exc), "process": process})
    if stopped:
        actions.append({"action": "stop_collectors", "ok": True, "processes": stopped})


def main():
    total, used, free = shutil.disk_usage(WATCH_PATH)
    used_pct = (used / total) * 100 if total else 0
    actions = []
    status = "ok"

    if used_pct >= WARN_PCT:
        status = "warning"
    if used_pct >= STOP_COLLECTION_PCT:
        status = "collection_paused"
        stop_collectors(actions)
    if used_pct >= CLOSE_WEB_PCT:
        status = "web_closed"
        stop_nginx(actions)
    elif used_pct <= REOPEN_WEB_PCT:
        start_nginx(actions)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "watchPath": str(WATCH_PATH),
        "thresholds": {
            "warnPct": WARN_PCT,
            "stopCollectionPct": STOP_COLLECTION_PCT,
            "closeWebPct": CLOSE_WEB_PCT,
            "reopenWebPct": REOPEN_WEB_PCT,
        },
        "disk": {
            "totalBytes": total,
            "usedBytes": used,
            "freeBytes": free,
            "usedPct": round(used_pct, 2),
        },
        "nginxActive": nginx_active(),
        "collectorProcesses": collector_processes(),
        "actions": actions,
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
