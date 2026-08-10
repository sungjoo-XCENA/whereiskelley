#!/usr/bin/env python3
import argparse
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = (ROOT / "data" / "guide").resolve()


def database_paths():
    configured = os.environ.get("WHEREISKELLEY_DB_PATH", "").strip()
    if configured:
        return [Path(configured).resolve()]
    return [
        (ROOT / "db" / "starwine.sqlite").resolve(),
        (ROOT / "db" / "starwine.collecting.sqlite").resolve(),
    ]


def clear_database_paths(path):
    if not path.exists():
        return 0
    with sqlite3.connect(path, timeout=120) as con:
        exists = con.execute(
            "select 1 from sqlite_master where type='table' and name='wine_list_sources'"
        ).fetchone()
        if not exists:
            return 0
        cursor = con.execute(
            """
            update wine_list_sources
            set content_path='', text_path=''
            where coalesce(content_path, '') like 'data/guide/%'
               or coalesce(text_path, '') like 'data/guide/%'
            """
        )
        con.commit()
        return max(0, cursor.rowcount)


def cache_files():
    if not CACHE_DIR.exists():
        return []
    files = []
    for path in CACHE_DIR.rglob("*"):
        if not path.is_file():
            continue
        path.resolve().relative_to(CACHE_DIR)
        files.append(path)
    return files


def main():
    parser = argparse.ArgumentParser(description="Remove obsolete guide source files while preserving source URLs and parsed DB rows.")
    parser.add_argument("--apply", action="store_true", help="Delete cache files and clear their obsolete DB path fields.")
    args = parser.parse_args()

    files = cache_files()
    total_bytes = sum(path.stat().st_size for path in files)
    print(f"cache_dir={CACHE_DIR}")
    print(f"files={len(files)} bytes={total_bytes}")
    if not args.apply:
        print("dry_run=true")
        return 0

    updated_rows = sum(clear_database_paths(path) for path in database_paths())
    deleted = 0
    for path in files:
        path.unlink(missing_ok=True)
        deleted += 1
    for directory in sorted(
        (path for path in CACHE_DIR.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.rmdir()
    print(f"deleted={deleted} database_rows_updated={updated_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
