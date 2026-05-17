import base64
import gzip
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "starwine.sqlite"
OUT_DIR = ROOT / "public" / "data"
WATCHLIST_PATH = OUT_DIR / "watchlist.json"
CHUNK_SIZE = 50


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def write_compressed_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_text(base64.b64encode(gzip.compress(raw, compresslevel=9)).decode("ascii") + "\n", encoding="ascii")


def normalize(value):
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def load_watchlist():
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            watches = data.get("watches") if isinstance(data, dict) else data
            if isinstance(watches, list):
                return [
                    {
                        "keyword": str(item.get("keyword", "")).strip(),
                        "vintage": str(item.get("vintage", "") or "").strip(),
                        "active": bool(item.get("active", True)),
                    }
                    for item in watches
                    if str(item.get("keyword", "")).strip()
                ]
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return [
        {"keyword": "Romanee-Conti", "vintage": "", "active": True},
        {"keyword": "William Kelley", "vintage": "", "active": True},
    ]


def row_count(con, sql):
    try:
        return con.execute(sql).fetchone()[0]
    except sqlite3.Error:
        return 0


def latest_run(con):
    try:
        row = con.execute("select * from sync_runs order by started_at desc limit 1").fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return {key: row[key] for key in row.keys()}


def result_row(row):
    venue_url = row["venue_url"] or ""
    venue_id = row["venue_slug"] or venue_url.rstrip("/").split("/")[-1] or f"venue-{row['venue_id']}"
    list_id = str(row["starwine_list_id"] or row["wine_list_id"])
    result = {
        "id": str(row["entry_id"]),
        "text": row["raw_text"] or "",
        "producer": row["producer"],
        "wineName": row["wine_name"],
        "vintage": row["vintage"],
        "region": row["region"],
        "grape": row["grape"],
        "priceValue": row["price_value"],
        "currency": row["currency"],
        "prices": [row["price_text"]] if row["price_text"] else [],
        "section": row["section"] or "Snapshot",
        "pageNumber": row["page_number"],
        "venue": {
            "id": venue_id,
            "name": row["venue_name"],
            "type": row["venue_type"],
            "city": row["city"],
            "country": row["country_name"],
            "regionSlug": row["region_slug"],
            "lat": row["lat"],
            "lng": row["lng"],
            "address": row["address"] or ", ".join([part for part in [row["city"], row["country_name"]] if part]),
            "googleMapsUrl": row["google_maps_url"] or "",
            "starWineMapUrl": row["starwine_map_url"] or "",
            "url": venue_url,
        },
        "wineList": {
            "id": list_id,
            "label": row["label"] or f"Wine list {list_id}",
            "externalUrl": row["external_url"] or "",
            "downloadUrl": row["download_url"] or "",
            "fileUrl": row["file_url"] or "",
            "fileViewUrl": row["file_view_url"] or "",
            "localFilePath": row["local_file_path"] or "",
            "localFileUrl": "",
            "updatedText": row["updated_text"] or "",
            "updatedDate": row["updated_date"] or "",
        },
    }
    return compact(result)


def guide_result_row(row):
    venue_id = f"guide-{row['target_id']}"
    list_id = str(row["source_id"] or f"guide-{row['target_id']}")
    result = {
        "id": f"guide-{row['entry_id']}",
        "source": "Guide DB",
        "text": row["raw_text"] or "",
        "producer": None,
        "wineName": None,
        "vintage": row["vintage"],
        "region": None,
        "grape": None,
        "priceValue": row["price_value"],
        "currency": row["currency"],
        "prices": [row["price_text"]] if row["price_text"] else [],
        "section": "Guide restaurant website",
        "pageNumber": None,
        "venue": {
            "id": venue_id,
            "name": row["name"],
            "type": "Restaurant",
            "city": row["city"],
            "country": row["country"],
            "lat": row["lat"],
            "lng": row["lng"],
            "address": row["address"] or ", ".join([part for part in [row["city"], row["country"]] if part]),
            "googleMapsUrl": "",
            "starWineMapUrl": "",
            "url": row["website_url"] or row["source_url"] or "",
        },
        "wineList": {
            "id": list_id,
            "label": row["source_type"] or "Guide wine list",
            "externalUrl": row["source_url"] or "",
            "downloadUrl": row["source_url"] or "",
            "fileUrl": row["source_url"] or "",
            "fileViewUrl": row["source_url"] or "",
            "localFilePath": row["content_path"] or "",
            "localFileUrl": "",
            "updatedText": row["last_seen_at"] or "",
            "updatedDate": row["last_seen_at"] or "",
        },
    }
    return compact(result)


def compact(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            item = compact(item)
            if item in (None, "", []):
                continue
            cleaned[key] = item
        return cleaned
    if isinstance(value, list):
        return [compact(item) for item in value if compact(item) not in (None, "", [])]
    return value


def load_lines(con):
    sql = """
        select
          e.id as entry_id,
          e.raw_text,
          e.producer,
          e.wine_name,
          e.vintage,
          e.region,
          e.grape,
          e.price_text,
          e.price_value,
          e.currency,
          e.section,
          e.page_number,
          v.id as venue_id,
          v.slug as venue_slug,
          v.name as venue_name,
          v.type as venue_type,
          v.city,
          v.region_slug,
          v.lat,
          v.lng,
          v.address,
          v.google_maps_url,
          v.starwine_map_url,
          v.venue_url,
          c.name as country_name,
          wl.id as wine_list_id,
          wl.starwine_list_id,
          wl.label,
          wl.download_url,
          wl.file_url,
          wl.file_view_url,
          wl.local_file_path,
          wl.updated_text,
          wl.updated_date,
          wl.file_url as external_url
        from wine_entries e
        join venues v on v.id = e.venue_id
        join countries c on c.id = v.country_id
        join wine_lists wl on wl.id = e.wine_list_id
        order by c.name, v.city, v.name, e.id
    """
    return [result_row(row) for row in con.execute(sql)]


def load_guide_lines(con):
    try:
        sql = """
            select
              e.id as entry_id,
              e.raw_text,
              e.vintage,
              e.price_text,
              e.price_value,
              e.currency,
              e.source_url,
              e.source_type,
              e.last_seen_at,
              t.id as target_id,
              t.name,
              t.country,
              t.city,
              t.address,
              t.lat,
              t.lng,
              t.website_url,
              s.id as source_id,
              s.content_path
            from guide_wine_entries e
            join restaurant_targets t on t.id = e.target_id
            left join wine_list_sources s on s.id = e.wine_list_source_id
            order by t.country, t.city, t.name, e.id
        """
        return [guide_result_row(row) for row in con.execute(sql)]
    except sqlite3.Error:
        return []


def load_venues(con):
    sql = """
        select
          v.id,
          v.slug,
          v.name,
          v.type,
          c.name as country,
          v.city,
          v.region_slug,
          v.lat,
          v.lng,
          v.address,
          v.google_maps_url,
          v.starwine_map_url,
          v.venue_url,
          count(distinct wl.id) as wine_list_count,
          count(e.id) as wine_line_count
        from venues v
        join countries c on c.id = v.country_id
        left join wine_lists wl on wl.venue_id = v.id
        left join wine_entries e on e.venue_id = v.id
        group by v.id
        order by c.name, v.city, v.name
    """
    return [{key: row[key] for key in row.keys()} for row in con.execute(sql)]


def watch_hits(watches, lines):
    hits = []
    seen = set()
    for watch in watches:
        if not watch.get("active", True):
            continue
        needle = normalize(watch["keyword"])
        vintage = watch.get("vintage", "")
        for line in lines:
            text = normalize(line.get("text"))
            if needle not in text:
                continue
            if vintage and str(line.get("vintage") or "") != vintage and vintage not in line.get("text", ""):
                continue
            key = (watch["keyword"], vintage, line["id"])
            if key in seen:
                continue
            seen.add(key)
            venue = line.get("venue") or {}
            wine_list = line.get("wineList") or {}
            hits.append(compact({
                "keyword": watch["keyword"],
                "vintage": vintage,
                "lineId": line.get("id"),
                "text": line.get("text"),
                "lineVintage": line.get("vintage"),
                "priceValue": line.get("priceValue"),
                "currency": line.get("currency"),
                "venue": {
                    "name": venue.get("name"),
                    "type": venue.get("type"),
                    "city": venue.get("city"),
                    "country": venue.get("country"),
                    "url": venue.get("url"),
                },
                "wineList": {
                    "id": wine_list.get("id"),
                    "downloadUrl": wine_list.get("downloadUrl"),
                    "updatedDate": wine_list.get("updatedDate"),
                },
            }))
    return hits


def clean_old_chunks():
    if not OUT_DIR.exists():
        return
    for path in OUT_DIR.glob("wine-lines-*.json"):
        path.unlink()
    for path in OUT_DIR.glob("wine-lines-*.json.gz.b64"):
        path.unlink()


def main():
    watches = load_watchlist()
    if not DB_PATH.exists():
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(WATCHLIST_PATH, {"watches": watches})
        write_json(OUT_DIR / "collection-status.json", {
            "generatedAt": now(),
            "status": "waiting",
            "message": "No local DB has been exported yet.",
            "counts": {"countries": 0, "cities": 0, "venues": 0, "wineLists": 0, "wineLines": 0},
            "lastRun": None,
            "chunks": [],
        })
        write_json(OUT_DIR / "venues.json", [])
        write_json(OUT_DIR / "watchlist-hits.json", {"generatedAt": now(), "hits": []})
        write_json(OUT_DIR / "search-manifest.json", {"generatedAt": now(), "chunks": [], "totalLines": 0})
        return

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    with con:
        lines = load_lines(con) + load_guide_lines(con)
        venues = load_venues(con)
        run = latest_run(con)
        chunks = []
        clean_old_chunks()
        for index in range(0, len(lines), CHUNK_SIZE):
            chunk_index = index // CHUNK_SIZE
            name = f"wine-lines-{chunk_index:03d}.json.gz.b64"
            chunk_lines = lines[index:index + CHUNK_SIZE]
            write_compressed_json(OUT_DIR / name, chunk_lines)
            chunks.append({"file": name, "count": len(chunk_lines), "encoding": "gzip-base64-json"})
        hits = watch_hits(watches, lines)
        status = "completed" if run and run.get("finished_at") else "ready"
        write_json(WATCHLIST_PATH, {"watches": watches})
        write_json(OUT_DIR / "venues.json", venues)
        write_json(OUT_DIR / "watchlist-hits.json", {"generatedAt": now(), "hits": hits})
        write_json(OUT_DIR / "search-manifest.json", {
            "generatedAt": now(),
            "chunks": chunks,
            "totalLines": len(lines),
        })
        write_json(OUT_DIR / "collection-status.json", {
            "generatedAt": now(),
            "status": status,
            "message": "Snapshot exported from the local collection DB.",
            "counts": {
                "countries": row_count(con, "select count(*) from countries"),
                "cities": row_count(con, "select count(*) from (select distinct country_id, city from venues where city is not null and city != '')"),
                "venues": len(venues),
                "wineLists": row_count(con, "select count(*) from wine_lists"),
                "wineLines": len(lines),
                "watchlistHits": len(hits),
            },
            "lastRun": run,
            "chunks": chunks,
        })


if __name__ == "__main__":
    main()
