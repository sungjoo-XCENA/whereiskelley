#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from publish_guide_snapshot import publish_guide_snapshot
from resource_monitor import monitor_process


ROOT = Path(__file__).resolve().parents[1]
PROGRESS_PATH = ROOT / "public" / "data" / "guide-progress.json"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def live_db_path():
    configured = os.environ.get("WHEREISKELLEY_DB_PATH", "").strip()
    return Path(configured) if configured else ROOT / "db" / "starwine.sqlite"


def remove_sqlite_files(path):
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        candidate.unlink(missing_ok=True)


def copy_sqlite(source, destination):
    remove_sqlite_files(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_con = sqlite3.connect(source, timeout=120)
    destination_con = sqlite3.connect(destination)
    try:
        source_con.execute("pragma busy_timeout=120000")
        source_con.backup(destination_con)
    finally:
        destination_con.close()
        source_con.close()


def reset_staging_collection(path):
    con = sqlite3.connect(path, timeout=120)
    try:
        con.execute("pragma busy_timeout=120000")
        con.execute("pragma foreign_keys=off")
        con.execute("delete from guide_wine_entries")
        con.execute("delete from wine_list_sources")
        con.execute(
            """
            update restaurant_targets
            set status=case
                  when website_url is null or trim(website_url)='' then 'missing_website'
                  else 'not_checked'
                end,
                last_checked_at=null,
                last_error=null
            """
        )
        con.commit()
    finally:
        con.close()


def update_progress(**changes):
    payload = {}
    if PROGRESS_PATH.exists():
        try:
            payload = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
    payload.update(changes)
    payload["generatedAt"] = now()
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = PROGRESS_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(PROGRESS_PATH)


def collection_failure_message(returncode):
    guard_path = ROOT / "public" / "data" / "server-guard.json"
    try:
        guard = json.loads(guard_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guard = {}
    if guard.get("status") == "collection_paused":
        used_pct = (guard.get("disk") or {}).get("usedPct")
        suffix = f" ({used_pct}% used)" if used_pct is not None else ""
        return f"Collection paused by the server disk guard{suffix}. The published database is unchanged."
    if returncode < 0:
        return f"Collection stopped by signal {-returncode}. The published database is unchanged."
    return f"Collection failed with exit code {returncode}. The published database is unchanged."


def main():
    parser = argparse.ArgumentParser(description="Collect into staging and publish only after success.")
    parser.add_argument("--max-links", type=int, default=60)
    parser.add_argument("--max-targets", type=int, default=0)
    parser.add_argument("--sleep", default="0.08")
    parser.add_argument("--workers", type=int, default=96)
    parser.add_argument("--source-workers", type=int, default=256)
    parser.add_argument("--pdf-workers", type=int, default=8)
    args = parser.parse_args()

    live_path = live_db_path().resolve()
    staging_path = live_path.with_name(f"{live_path.stem}.collecting{live_path.suffix}")
    if not live_path.exists():
        raise FileNotFoundError(f"Live DB does not exist: {live_path}")

    update_progress(
        status="preparing",
        phase="preparing_staging",
        message="Preparing a separate collection database. Current search data remains available.",
        workerConfig={
            "discovery": args.workers,
            "html": args.source_workers,
            "pdf": args.pdf_workers,
            "targetCpuPercent": float(os.environ.get("WHEREISKELLEY_TARGET_CPU_PERCENT", "80")),
            "maxMemoryPercent": float(os.environ.get("WHEREISKELLEY_MAX_MEMORY_PERCENT", "80")),
            "maxDiskPercent": float(os.environ.get("WHEREISKELLEY_MAX_DISK_PERCENT", "85")),
        },
    )
    copy_sqlite(live_path, staging_path)
    reset_staging_collection(staging_path)

    env = os.environ.copy()
    env["WHEREISKELLEY_DB_PATH"] = str(staging_path)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "guide_discover_wine_lists.py"),
        "--skip-google",
        "--only-with-website",
        "--recheck-all",
        "--replace-existing",
        "--max-links",
        str(args.max_links),
        "--sleep",
        str(args.sleep),
        "--workers",
        str(max(1, args.workers)),
        "--source-workers",
        str(max(1, args.source_workers)),
        "--pdf-workers",
        str(max(1, args.pdf_workers)),
    ]
    if args.max_targets > 0:
        command.extend(["--max-targets", str(args.max_targets)])

    process = subprocess.Popen(command, cwd=ROOT, env=env)
    return_code = monitor_process(process)
    if return_code != 0:
        update_progress(
            status="failed",
            phase="collection_failed",
            message=collection_failure_message(return_code),
        )
        return return_code

    if args.max_targets > 0:
        remove_sqlite_files(staging_path)
        update_progress(
            status="completed_test",
            phase="completed_test",
            message="Partial test collection completed. The published database was not changed.",
            currentTarget="",
            currentUrl="",
        )
        return 0

    update_progress(
        status="publishing",
        phase="publishing",
        message="Collection finished. Publishing the completed snapshot.",
    )
    publish_guide_snapshot(staging_path, live_path)

    export_env = os.environ.copy()
    export_env["WHEREISKELLEY_DB_PATH"] = str(live_path)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_snapshot.py")],
        cwd=ROOT,
        env=export_env,
        check=False,
    )
    remove_sqlite_files(staging_path)
    update_progress(
        status="completed",
        phase="completed",
        message="Collection completed and the new database snapshot is live.",
        currentTarget="",
        currentUrl="",
        remainingTargets=0,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
