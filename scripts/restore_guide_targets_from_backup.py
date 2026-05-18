import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "starwine.sqlite"


def count(con, table):
    return con.execute(f"select count(*) from {table}").fetchone()[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_db")
    args = parser.parse_args()

    backup_db = Path(args.backup_db)
    if not backup_db.is_absolute():
        backup_db = ROOT / backup_db
    if not backup_db.exists():
        raise SystemExit(f"Backup DB not found: {backup_db}")

    with sqlite3.connect(DB_PATH) as con:
        con.execute("pragma foreign_keys=off")
        con.execute("attach database ? as old", (str(backup_db),))
        for table in [
            "guide_wine_entries",
            "wine_list_sources",
            "guide_rankings",
            "guide_places",
            "restaurant_targets",
            "guide_sources",
            "guide_collection_runs",
        ]:
            con.execute(f"delete from {table}")
        for table in ["guide_sources", "guide_places", "guide_rankings", "restaurant_targets"]:
            con.execute(f"insert into {table} select * from old.{table}")
        con.execute(
            """
            update restaurant_targets
            set status='not_checked',
                last_checked_at=null,
                last_error=null
            """
        )
        con.commit()
        con.execute("detach database old")
        con.execute("pragma foreign_keys=on")

        tables = [
            "restaurant_targets",
            "guide_places",
            "guide_rankings",
            "wine_list_sources",
            "guide_wine_entries",
            "guide_collection_runs",
        ]
        sources = con.execute(
            """
            select s.code, count(*)
            from guide_places gp
            join guide_sources s on s.id=gp.source_id
            group by s.code
            order by 2 desc
            """
        ).fetchall()
        payload = {
            "counts": {table: count(con, table) for table in tables},
            "sources": sources,
            "withWebsite": con.execute(
                "select count(*) from restaurant_targets where website_url is not null and length(website_url)>0"
            ).fetchone()[0],
            "mapped": con.execute(
                "select count(*) from restaurant_targets where lat is not null and lng is not null"
            ).fetchone()[0],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
