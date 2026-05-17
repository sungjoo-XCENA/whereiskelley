import json
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "starwine.sqlite"


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def count(con, sql):
    try:
        return con.execute(sql).fetchone()[0]
    except sqlite3.Error:
        return 0


def stats_payload():
    if not DB_PATH.exists():
        return {
            "countryCount": 0,
            "cityCount": 0,
            "venueCount": 0,
            "wineListCount": 0,
            "entryCount": 0,
            "lastRun": None,
            "collectorConfigured": False,
        }
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    with con:
        latest = con.execute(
            "select * from sync_runs order by started_at desc limit 1"
        ).fetchone()
        return {
            "countryCount": count(con, "select count(*) from countries"),
            "cityCount": count(con, "select count(*) from (select distinct country_id, city from venues where city is not null and city != '')"),
            "venueCount": count(con, "select count(*) from venues"),
            "wineListCount": count(con, "select count(*) from wine_lists"),
            "entryCount": count(con, "select count(*) from wine_entries"),
            "lastRun": row_to_dict(latest) if latest else None,
            "collectorConfigured": latest is not None,
        }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            json_response(self, stats_payload())
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=500)
