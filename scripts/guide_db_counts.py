import json
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


DB_PATH = Path(os.environ.get("WHEREISKELLEY_DB_PATH", "").strip() or ROOT / "db" / "starwine.sqlite")


with sqlite3.connect(DB_PATH) as con:
    cur = con.cursor()
    payload = {
        "target_status": cur.execute(
            "select status, count(*) from restaurant_targets group by status order by status"
        ).fetchall(),
        "source_status": cur.execute(
            "select status, ifnull(parser_status, ''), count(*) from wine_list_sources group by status, parser_status order by 3 desc"
        ).fetchall(),
        "source_count": cur.execute("select count(*) from wine_list_sources").fetchone()[0],
        "line_count": cur.execute("select count(*) from guide_wine_entries").fetchone()[0],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
