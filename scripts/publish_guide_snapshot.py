#!/usr/bin/env python3
import argparse
import sqlite3
from pathlib import Path


TARGET_COLUMNS = (
    "id, normalized_key, name, normalized_name, country, city, address, lat, lng, "
    "website_url, sources_json, source_count, priority, status, last_checked_at, "
    "last_error, first_seen_at, last_seen_at"
)
SOURCE_COLUMNS = (
    "id, target_id, url, source_type, status, content_path, text_path, checksum, "
    "discovered_at, last_checked_at, parser_status, line_count, last_error"
)
ENTRY_COLUMNS = (
    "id, target_id, wine_list_source_id, raw_text, vintage, price_text, price_value, "
    "currency, source_url, source_type, status, first_seen_at, last_seen_at"
)
RUN_COLUMNS = (
    "id, started_at, finished_at, status, sources_requested, target_count, "
    "websites_checked, wine_lists_found, wine_lines_found, watch_hits, errors, notes"
)


def publish_guide_snapshot(staging_path, live_path):
    staging_path = Path(staging_path).resolve()
    live_path = Path(live_path).resolve()
    if not staging_path.exists():
        raise FileNotFoundError(f"Staging DB does not exist: {staging_path}")
    if not live_path.exists():
        raise FileNotFoundError(f"Live DB does not exist: {live_path}")

    con = sqlite3.connect(live_path, timeout=120)
    try:
        con.execute("pragma busy_timeout=120000")
        con.execute("pragma foreign_keys=off")
        con.execute("attach database ? as staged", (str(staging_path),))
        con.execute("begin immediate")

        con.execute(
            f"insert or ignore into restaurant_targets ({TARGET_COLUMNS}) "
            f"select {TARGET_COLUMNS} from staged.restaurant_targets"
        )
        for column in (
            "normalized_key", "name", "normalized_name", "country", "city", "address",
            "lat", "lng", "website_url", "sources_json", "source_count", "priority",
            "status", "last_checked_at", "last_error", "first_seen_at", "last_seen_at",
        ):
            con.execute(
                f"update restaurant_targets set {column}=("
                f"select staged_target.{column} from staged.restaurant_targets staged_target "
                "where staged_target.id=restaurant_targets.id) "
                "where exists (select 1 from staged.restaurant_targets staged_target "
                "where staged_target.id=restaurant_targets.id)"
            )

        con.execute("delete from guide_wine_entries")
        con.execute("delete from wine_list_sources")
        con.execute(
            f"insert into wine_list_sources ({SOURCE_COLUMNS}) "
            f"select {SOURCE_COLUMNS} from staged.wine_list_sources"
        )
        con.execute(
            f"insert into guide_wine_entries ({ENTRY_COLUMNS}) "
            f"select {ENTRY_COLUMNS} from staged.guide_wine_entries"
        )
        con.execute(
            f"insert or replace into guide_collection_runs ({RUN_COLUMNS}) "
            f"select {RUN_COLUMNS} from staged.guide_collection_runs"
        )
        con.commit()
        con.execute("detach database staged")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description="Atomically publish completed guide collection tables.")
    parser.add_argument("staging_db")
    parser.add_argument("live_db")
    args = parser.parse_args()
    publish_guide_snapshot(args.staging_db, args.live_db)


if __name__ == "__main__":
    main()
