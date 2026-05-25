import io
import json
import mimetypes
import os
import subprocess
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
SNAPSHOT_STATUS_PATH = PUBLIC_DIR / "data" / "collection-status.json"
GUIDE_PROGRESS_PATH = PUBLIC_DIR / "data" / "guide-progress.json"
GUIDE_STATUS_PATH = PUBLIC_DIR / "data" / "guide-status.json"


def load_local_env():
    for env_path in (
        ROOT / ".env.local",
        ROOT / ".env",
        ROOT.parent.parent / ".env.local",
        ROOT.parent.parent / ".env",
    ):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lstrip("\ufeff")
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env()


def resolve_db_path():
    configured = os.environ.get("WHEREISKELLEY_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    candidates = [
        ROOT / "db" / "starwine.sqlite",
        ROOT.parent.parent / "db" / "starwine.sqlite",
    ]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return candidates[0]
    return max(existing, key=lambda path: path.stat().st_size)


DB_PATH = resolve_db_path()
PORT = 4317
HOST = os.environ.get("WHEREISKELLEY_HOST", "127.0.0.1")
API_TOKEN = os.environ.get("WHEREISKELLEY_API_TOKEN", "").strip()
ADMIN_PASSWORD = os.environ.get("WHEREISKELLEY_ADMIN_PASSWORD", "").strip()
ALLOWED_ORIGIN = os.environ.get("WHEREISKELLEY_ALLOWED_ORIGIN", "*").strip() or "*"
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_search_api


COLLECTOR_PROCESS = None


PRICE_TOKEN_RE = sync_search_api.re.compile(
    rf"(?:{sync_search_api.PRICE_CURRENCY_RE})?\s*(?:\d{{1,3}}(?:[,\s.]\d{{3}})+|\d{{2,6}}[oO]\s*[,\.]\s*[oO0]{{2}}|\d{{2,6}}(?:\s*[,\.]\s*[oO0]{{2}})?)(?!\d)",
    sync_search_api.re.I,
)


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("access-control-allow-origin", ALLOWED_ORIGIN)
    handler.send_header("access-control-allow-headers", "content-type, x-whereiskelley-token")
    handler.send_header("access-control-allow-methods", "GET, OPTIONS")
    handler.send_header("access-control-allow-private-network", "true")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def collector_is_running():
    global COLLECTOR_PROCESS
    if COLLECTOR_PROCESS is None:
        return False
    if COLLECTOR_PROCESS.poll() is None:
        return True
    COLLECTOR_PROCESS = None
    return False


def start_wine_collection(payload):
    global COLLECTOR_PROCESS
    if not ADMIN_PASSWORD:
        return {
            "ok": False,
            "error": "Admin password is not configured on the local server.",
            "hint": "Set WHEREISKELLEY_ADMIN_PASSWORD in .env.local, then restart run-server.ps1.",
        }, 503
    if str(payload.get("password") or "") != ADMIN_PASSWORD:
        return {"ok": False, "error": "Wrong password."}, 401
    if collector_is_running():
        return {"ok": True, "running": True, "message": "Collection is already running.", "pid": COLLECTOR_PROCESS.pid}, 200

    max_links = int(payload.get("maxLinks") or os.environ.get("WHEREISKELLEY_COLLECT_MAX_LINKS", "12"))
    max_targets = int(payload.get("maxTargets") or 0)
    sleep_seconds = str(payload.get("sleep") or os.environ.get("WHEREISKELLEY_COLLECT_SLEEP", "0.08"))
    command = [
        sys.executable,
        str(SCRIPTS_DIR / "guide_discover_wine_lists.py"),
        "--skip-google",
        "--only-with-website",
        "--recheck-all",
        "--replace-existing",
        "--max-links",
        str(max_links),
        "--sleep",
        sleep_seconds,
    ]
    if max_targets > 0:
        command.extend(["--max-targets", str(max_targets)])

    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = open(log_dir / "web-recollect.log", "ab")
    stderr = open(log_dir / "web-recollect.err.log", "ab")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        COLLECTOR_PROCESS = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=stdout,
            stderr=stderr,
            env=env,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()
    return {
        "ok": True,
        "running": True,
        "pid": COLLECTOR_PROCESS.pid,
        "message": "Wine-list recollection started on the local PC.",
        "command": " ".join(command),
    }, 202


def text_response(handler, text, status=200):
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "text/plain; charset=utf-8")
    handler.send_header("access-control-allow-origin", ALLOWED_ORIGIN)
    handler.send_header("access-control-allow-headers", "content-type, x-whereiskelley-token")
    handler.send_header("access-control-allow-methods", "GET, OPTIONS")
    handler.send_header("access-control-allow-private-network", "true")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def javascript_response(handler, text, status=200):
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/javascript; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("access-control-allow-origin", ALLOWED_ORIGIN)
    handler.send_header("access-control-allow-headers", "content-type, x-whereiskelley-token")
    handler.send_header("access-control-allow-methods", "GET, OPTIONS")
    handler.send_header("access-control-allow-private-network", "true")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def config_js():
    payload = {
        "googleMapsApiKey": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
    }
    return f"window.STARWINE_CONFIG = {json.dumps(payload)};"


def ensure_db():
    if not DB_PATH.exists():
        raise RuntimeError("Database is missing. Run scripts\\sync.ps1 or scripts\\sync.py first.")


def stats():
    if SNAPSHOT_STATUS_PATH.exists():
        snapshot = json.loads(SNAPSHOT_STATUS_PATH.read_text(encoding="utf-8"))
        counts = snapshot.get("counts") or {}
        return {
            "countryCount": counts.get("countries", 0),
            "cityCount": counts.get("cities", 0),
            "venueCount": counts.get("venues", 0),
            "wineListCount": counts.get("wineLists", 0),
            "entryCount": counts.get("wineLines", 0),
            "watchlistHitCount": counts.get("watchlistHits", 0),
            "lastRun": snapshot.get("lastRun"),
            "collectorConfigured": bool(snapshot.get("lastRun")),
            "snapshot": snapshot,
        }
    ensure_db()
    with connect() as con:
        latest = con.execute(
            "select * from sync_runs order by started_at desc limit 1"
        ).fetchone()
        country_count = con.execute("select count(*) from countries").fetchone()[0]
        city_count = con.execute(
            "select count(*) from (select distinct country_id, city from venues where city is not null and city != '')"
        ).fetchone()[0]
        return {
            "countryCount": country_count,
            "cityCount": city_count,
            "venueCount": con.execute("select count(*) from venues").fetchone()[0],
            "wineListCount": con.execute("select count(*) from wine_lists").fetchone()[0],
            "entryCount": con.execute("select count(*) from wine_entries").fetchone()[0],
            "lastRun": row_to_dict(latest) if latest else None,
        }


def read_json_file(path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return fallback


def mark_stale_progress(progress):
    if not isinstance(progress, dict) or progress.get("status") != "running":
        return progress
    generated_at = progress.get("generatedAt")
    if not generated_at:
        return progress
    try:
        updated_at = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return progress
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    stale_seconds = int((datetime.now(timezone.utc) - updated_at).total_seconds())
    if stale_seconds <= 15 * 60:
        return progress
    stalled = dict(progress)
    stalled["status"] = "stalled"
    stalled["phase"] = "stalled"
    stalled["stale"] = True
    stalled["staleSeconds"] = stale_seconds
    stalled["message"] = "Collector stopped reporting progress. Restart the local collection to continue."
    return stalled


def guide_collection_status():
    progress = mark_stale_progress(read_json_file(GUIDE_PROGRESS_PATH, {}))
    snapshot = read_json_file(GUIDE_STATUS_PATH, {})
    progress_counts = progress.get("dbCounts") if isinstance(progress.get("dbCounts"), dict) else {}
    payload = {
        "generatedAt": progress.get("generatedAt") or snapshot.get("generatedAt"),
        "progress": progress,
        "snapshot": snapshot,
        "counts": {
            "targets": 0,
            "withWebsite": 0,
            "websitesChecked": int(progress.get("websitesChecked") or 0),
            "wineListSources": 0,
            "wineLines": 0,
            "errors": int(progress.get("errors") or 0),
            "review": 0,
        },
        "statusCounts": [],
        "sourceStatusCounts": [],
        "collectionSummary": {
            "totalTargets": 0,
            "checkedTargets": 0,
            "foundWineList": 0,
            "noWineList": 0,
            "pending": 0,
            "missingWebsite": 0,
            "needsReview": 0,
            "errors": 0,
            "parseReviewSources": 0,
            "parsedSources": 0,
            "emptyParsedSources": 0,
            "mappedTargets": 0,
        },
        "mapTargets": [],
        "recentErrors": [],
        "latestRuns": [],
    }
    if not DB_PATH.exists():
        return payload
    with connect() as con:
        payload["counts"].update({
            "targets": con.execute("select count(1) from restaurant_targets").fetchone()[0],
            "withWebsite": con.execute(
                "select count(1) from restaurant_targets where website_url is not null and length(website_url)>0"
            ).fetchone()[0],
            "wineListSources": con.execute("select count(1) from wine_list_sources").fetchone()[0],
            "wineLines": con.execute("select count(1) from guide_wine_entries").fetchone()[0],
            "review": con.execute("select count(1) from restaurant_targets where status in ('review','error')").fetchone()[0],
        })
        payload["statusCounts"] = [
            row_to_dict(row)
            for row in con.execute(
                "select status, count(1) as count from restaurant_targets group by status order by count desc"
            )
        ]
        payload["sourceStatusCounts"] = [
            row_to_dict(row)
            for row in con.execute(
                """
                select coalesce(parser_status, status, 'unknown') as status, count(1) as count
                from wine_list_sources
                group by coalesce(parser_status, status, 'unknown')
                order by count desc
                """
            )
        ]
        target_summary = con.execute(
            """
            select
              count(1) as totalTargets,
              sum(case when status != 'not_checked' then 1 else 0 end) as checkedTargets,
              sum(case when status = 'no_wine_list' then 1 else 0 end) as noWineList,
              sum(case when status = 'not_checked' then 1 else 0 end) as pending,
              sum(case when status = 'missing_website' then 1 else 0 end) as missingWebsite,
              sum(case when status in ('review','error') then 1 else 0 end) as needsReview,
              sum(case when status = 'error' then 1 else 0 end) as errors,
              sum(case when status != 'not_checked' and lat is not null and lng is not null then 1 else 0 end) as mappedTargets,
              sum(case when status != 'not_checked' and lat is not null and lng is not null and website_url is not null and trim(website_url) != '' then 1 else 0 end) as mappedWithWebsite
            from restaurant_targets
            """
        ).fetchone()
        source_summary = con.execute(
            """
            select
              count(1) as totalSources,
              count(distinct case when status = 'found' and parser_status = 'parsed' and coalesce(line_count, 0) > 0 then target_id end) as foundWineList,
              sum(case when status = 'found' and parser_status = 'parsed' and coalesce(line_count, 0) > 0 then 1 else 0 end) as parsedSources,
              sum(case when status != 'found' or parser_status != 'parsed' or coalesce(line_count, 0) = 0 or (last_error is not null and last_error != '') then 1 else 0 end) as parseReviewSources,
              sum(case when parser_status = 'parsed' and coalesce(line_count, 0) = 0 then 1 else 0 end) as emptyParsedSources
            from wine_list_sources
            """
        ).fetchone()
        summary = row_to_dict(target_summary)
        summary.update(row_to_dict(source_summary))
        payload["collectionSummary"].update({key: int(value or 0) for key, value in summary.items()})
        payload["recentErrors"] = [
            row_to_dict(row)
            for row in con.execute(
                """
                select
                  coalesce(nullif(last_error, ''), 'Unknown error') as error,
                  count(1) as count
                from restaurant_targets
                where last_error is not null and last_error != ''
                group by coalesce(nullif(last_error, ''), 'Unknown error')
                order by count desc, error asc
                limit 10
                """
            )
        ]
        payload["mapTargets"] = [
            row_to_dict(row)
            for row in con.execute(
                """
                with source_counts as (
                  select target_id, count(1) as source_count,
                         sum(case when status = 'found' and parser_status = 'parsed' and coalesce(line_count, 0) > 0 then 1 else 0 end) as verified_source_count,
                         sum(case when status != 'found' or parser_status != 'parsed' or coalesce(line_count, 0) = 0 or (last_error is not null and last_error != '') then 1 else 0 end) as review_source_count
                  from wine_list_sources
                  group by target_id
                ),
                entry_counts as (
                  select target_id, count(1) as line_count
                  from guide_wine_entries
                  group by target_id
                ),
                wine_choices as (
                  select target_id, url, source_type, status as source_status, parser_status, line_count
                  from (
                    select
                      s.target_id,
                      s.url,
                      s.source_type,
                      s.status,
                      s.parser_status,
                      s.line_count,
                      row_number() over (
                        partition by s.target_id
                        order by
                          case when s.status = 'found' and s.parser_status = 'parsed' and coalesce(s.line_count, 0) > 0 then 0 else 1 end,
                          case when rt.website_url is not null and rt.website_url != '' and s.url = rt.website_url then 1 else 0 end,
                          case when s.source_type = 'pdf' then 0 else 1 end,
                          case
                            when lower(s.url) like '%wine%' or lower(s.url) like '%vin%' or lower(s.url) like '%wein%'
                              or lower(s.url) like '%drink%' or lower(s.url) like '%beverage%' or lower(s.url) like '%pdf%'
                            then 0 else 1
                          end,
                          coalesce(s.line_count, 0) desc,
                          s.last_checked_at desc,
                          s.discovered_at desc
                      ) as choice_rank
                    from wine_list_sources s
                    join restaurant_targets rt on rt.id = s.target_id
                  )
                  where choice_rank = 1
                )
                select
                  t.id,
                  t.name,
                  t.city,
                  t.country,
                  t.address,
                  t.lat,
                  t.lng,
                  t.website_url as websiteUrl,
                  t.status,
                  t.last_checked_at as lastCheckedAt,
                  t.last_error as lastError,
                  wc.url as wineListUrl,
                  wc.source_type as wineListType,
                  wc.source_status as wineListStatus,
                  wc.parser_status as wineListParserStatus,
                  coalesce(wc.line_count, 0) as chosenWineLineCount,
                  coalesce(sc.source_count, 0) as wineListCount,
                  coalesce(sc.verified_source_count, 0) as verifiedWineListCount,
                  coalesce(sc.review_source_count, 0) as reviewSourceCount,
                  coalesce(ec.line_count, 0) as wineLineCount
                from restaurant_targets t
                left join source_counts sc on sc.target_id = t.id
                left join entry_counts ec on ec.target_id = t.id
                left join wine_choices wc on wc.target_id = t.id
                where t.status != 'not_checked'
                  and t.lat is not null
                  and t.lng is not null
                  and t.website_url is not null
                  and trim(t.website_url) != ''
                order by
                  case
                    when t.status = 'found' then 0
                    when t.status = 'no_wine_list' then 1
                    when t.status in ('review','error') then 2
                    else 3
                  end,
                  t.name asc
                limit 7000
                """
            )
        ]
        payload["latestRuns"] = [
            row_to_dict(row)
            for row in con.execute(
                """
                select id, status, started_at, finished_at, target_count, websites_checked,
                       wine_lists_found, wine_lines_found, watch_hits, errors, notes
                from guide_collection_runs
                order by id desc
                limit 5
                """
            )
        ]
    for key in ["wineListSources", "wineLines", "review"]:
        payload["counts"][key] = max(int(payload["counts"].get(key) or 0), int(progress_counts.get(key) or 0))
    payload["collectionSummary"]["totalSources"] = max(
        int(payload["collectionSummary"].get("totalSources") or 0),
        int(payload["counts"].get("wineListSources") or 0),
        int(progress.get("wineListsFound") or 0),
    )
    payload["collectionSummary"]["parseReviewSources"] = max(
        int(payload["collectionSummary"].get("parseReviewSources") or 0),
        max(0, int(payload["collectionSummary"].get("totalSources") or 0) - int(payload["collectionSummary"].get("parsedSources") or 0)),
    )
    return payload


def normalize_watch_text(value):
    folded = fold_text(value or "")
    return " ".join(sync_search_api.re.findall(r"[a-z0-9]+", folded))


def watch_matches_text(raw_text, keyword, vintage=""):
    haystack = normalize_watch_text(raw_text)
    tokens = [token for token in normalize_watch_text(keyword).split() if token]
    if not tokens or not all(token in haystack for token in tokens):
        return False
    year = str(vintage or "").strip()
    return not year or year in str(raw_text or "")


def parse_watchlist_param(params):
    raw = params.get("watchlist", [""])[0]
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [
                    {
                        "keyword": str(item.get("keyword") or "").strip(),
                        "vintage": str(item.get("vintage") or "").strip(),
                    }
                    for item in parsed
                    if isinstance(item, dict) and str(item.get("keyword") or "").strip()
                ]
        except json.JSONDecodeError:
            pass
    keyword = params.get("keyword", [""])[0].strip()
    vintage = params.get("vintage", [""])[0].strip()
    return [{"keyword": keyword, "vintage": vintage}] if keyword else []


def comparable_time(value):
    return str(value or "").replace("T", " ").replace("+00:00", "")


def guide_watch(params):
    ensure_db()
    watches = parse_watchlist_param(params)
    limit_per_watch = min(int(params.get("limit", ["80"])[0] or 80), 300)
    if not watches:
        return {"generatedAt": None, "watches": [], "rows": [], "totals": {"matches": 0, "restaurants": 0, "newRestaurants": 0, "staleRestaurants": 0}}
    with connect() as con:
        latest_completed = con.execute(
            """
            select started_at, finished_at
            from guide_collection_runs
            where status='completed' and finished_at is not null
            order by id desc
            limit 1
            """
        ).fetchone()
        latest_run = con.execute(
            "select started_at, status from guide_collection_runs order by id desc limit 1"
        ).fetchone()
        rows = [
            row_to_dict(row)
            for row in con.execute(
                """
                select e.raw_text, e.vintage, e.price_text, e.price_value, e.currency,
                       e.source_url, e.source_type, e.status,
                       e.first_seen_at, e.last_seen_at,
                       t.name, t.city, t.country, t.website_url, t.status as target_status,
                       t.last_checked_at
                from guide_wine_entries e
                join restaurant_targets t on t.id = e.target_id
                order by e.last_seen_at desc, t.name asc
                """
            )
        ]
    completed_at = latest_completed["finished_at"] if latest_completed else ""
    running_started_at = latest_run["started_at"] if latest_run and latest_run["status"] == "running" else ""
    watch_payloads = []
    all_rows = []
    for watch in watches:
        matches = []
        for row in rows:
            if not watch_matches_text(row.get("raw_text"), watch["keyword"], watch.get("vintage")):
                continue
            restaurant_key = "|".join([row.get("name") or "", row.get("city") or "", row.get("country") or ""])
            is_new = bool(completed_at and comparable_time(row.get("first_seen_at")) > comparable_time(completed_at))
            is_stale = bool(
                running_started_at
                and row.get("last_checked_at")
                and comparable_time(row.get("last_checked_at")) >= comparable_time(running_started_at)
                and comparable_time(row.get("last_seen_at")) < comparable_time(running_started_at)
            )
            item = {
                **row,
                "keyword": watch["keyword"],
                "watchVintage": watch.get("vintage") or "",
                "restaurantKey": restaurant_key,
                "isNewRestaurant": is_new,
                "isStaleRestaurant": is_stale,
            }
            matches.append(item)
        restaurant_keys = {row["restaurantKey"] for row in matches}
        new_restaurants = sorted({row["restaurantKey"] for row in matches if row["isNewRestaurant"]})
        stale_restaurants = sorted({row["restaurantKey"] for row in matches if row["isStaleRestaurant"]})
        watch_payloads.append(
            {
                "keyword": watch["keyword"],
                "vintage": watch.get("vintage") or "",
                "matchCount": len(matches),
                "restaurantCount": len(restaurant_keys),
                "newRestaurantCount": len(new_restaurants),
                "staleRestaurantCount": len(stale_restaurants),
                "newRestaurants": new_restaurants[:20],
                "staleRestaurants": stale_restaurants[:20],
                "rows": matches[:limit_per_watch],
            }
        )
        all_rows.extend(matches[:limit_per_watch])
    return {
        "generatedAt": guide_collection_status().get("generatedAt"),
        "watches": watch_payloads,
        "rows": all_rows,
        "totals": {
            "matches": sum(watch["matchCount"] for watch in watch_payloads),
            "restaurants": len({row["restaurantKey"] for row in all_rows}),
            "newRestaurants": sum(watch["newRestaurantCount"] for watch in watch_payloads),
            "staleRestaurants": sum(watch["staleRestaurantCount"] for watch in watch_payloads),
        },
        "comparison": {
            "latestCompletedAt": completed_at,
            "currentRunStartedAt": running_started_at,
            "staleMeans": "A previously saved watched-wine row was not seen again after that restaurant was checked in the current run.",
        },
    }


def filters():
    ensure_db()
    with connect() as con:
        countries = [
            row["name"]
            for row in con.execute("select name from countries order by name").fetchall()
        ]
        cities = [
            row["city"]
            for row in con.execute(
                "select distinct city from venues where city is not null and city != '' order by city"
            ).fetchall()
        ]
        return {"countries": countries, "cities": cities}


def search(params):
    ensure_db()
    q = params.get("q", [""])[0].strip()
    country = params.get("country", [""])[0].strip()
    city = params.get("city", [""])[0].strip()
    vintage = params.get("vintage", [""])[0].strip()
    limit = min(int(params.get("limit", ["500"])[0] or 500), 5000)
    live = params.get("live", ["0"])[0] == "1"
    live_pages_raw = params.get("livePages", ["2"])[0] or "2"
    live_page_cap = min(int(params.get("livePageCap", ["200"])[0] or 200), 300)
    live_pages = live_pages_raw if live_pages_raw == "all" else min(int(live_pages_raw), live_page_cap)
    live_max_pdfs = min(int(params.get("liveMaxPdfs", ["3"])[0] or 3), 50)
    live_refresh = None
    live_source_ids = []
    if live and q:
        live_query = q if not vintage or vintage in q else f"{q} {vintage}"
        live_refresh = refresh_from_search_api(live_query, live_pages, live_max_pdfs, live_page_cap)
        live_source_ids = live_refresh["sourceItemIds"]

    where = []
    args = []
    use_fts = bool(q) and not live_source_ids
    if live_source_ids:
        placeholders = ",".join("?" for _ in live_source_ids)
        where.append(f"e.source_item_id in ({placeholders})")
        args.extend(live_source_ids)
    elif use_fts:
        where.append("wine_entries_fts match ?")
        args.append(q.replace('"', " "))
    if country:
        where.append("c.name = ?")
        args.append(country)
    if city:
        where.append("v.city like ?")
        args.append(f"%{city}%")
    if vintage:
        where.append("e.vintage = ?")
        args.append(vintage)

    where_sql = f"where {' and '.join(where)}" if where else ""
    join_fts = "join wine_entries_fts fts on fts.rowid = e.id" if use_fts else ""
    sql = f"""
        select
            e.id,
            e.raw_text as text,
            e.producer,
            e.wine_name as wineName,
            e.vintage,
            e.region,
            e.grape,
            e.price_text as priceText,
            e.price_value as priceValue,
            e.currency,
            e.section,
            e.page_number as pageNumber,
            wl.id as wineListId,
            wl.label as wineListLabel,
            wl.download_url as downloadUrl,
            wl.file_url as fileUrl,
            wl.file_view_url as fileViewUrl,
            wl.local_file_path as localFilePath,
            wl.text_file_path as textFilePath,
            wl.updated_text as updatedText,
            wl.updated_date as updatedDate,
            v.id as venueId,
            v.name as venueName,
            v.type as venueType,
            v.city,
            v.region_slug as regionSlug,
            v.lat,
            v.lng,
            v.address,
            v.google_maps_url as googleMapsUrl,
            v.starwine_map_url as starWineMapUrl,
            v.venue_url as venueUrl,
            c.name as country
        from wine_entries e
        {join_fts}
        join wine_lists wl on wl.id = e.wine_list_id
        join venues v on v.id = e.venue_id
        join countries c on c.id = v.country_id
        {where_sql}
        order by
          case when e.price_value is null then 1 else 0 end,
          e.price_value asc,
          wl.updated_date desc,
          v.name asc,
          e.id asc
        limit ?
    """
    args.append(limit)

    with connect() as con:
        rows = con.execute(sql, args).fetchall()
    results = []
    for row in rows:
        item = row_to_dict(row)
        price_text = item.pop("priceText") or ""
        item["prices"] = [price_text] if price_text else []
        item["venue"] = {
            "id": item.pop("venueId"),
            "name": item.pop("venueName"),
            "type": item.pop("venueType"),
            "city": item.pop("city"),
            "country": item.pop("country"),
            "regionSlug": item.pop("regionSlug"),
            "lat": item.pop("lat"),
            "lng": item.pop("lng"),
            "address": item.pop("address"),
            "googleMapsUrl": item.pop("googleMapsUrl"),
            "starWineMapUrl": item.pop("starWineMapUrl"),
            "url": item.pop("venueUrl"),
        }
        item["wineList"] = {
            "id": item.pop("wineListId"),
            "label": item.pop("wineListLabel"),
            "downloadUrl": item.pop("downloadUrl"),
            "fileUrl": item.pop("fileUrl"),
            "fileViewUrl": item.pop("fileViewUrl"),
            "localFilePath": item.pop("localFilePath"),
            "textFilePath": item.pop("textFilePath"),
            "updatedText": item.pop("updatedText"),
            "updatedDate": item.pop("updatedDate"),
        }
        item["wineList"]["localFileUrl"] = f"/files/{item['wineList']['localFilePath']}" if item["wineList"]["localFilePath"] else ""
        results.append(item)
    return {"query": q, "count": len(results), "results": results, "liveRefresh": live_refresh}


def fold_text(value):
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def clean_fragment(value):
    text = sync_search_api.re.sub(r"(?<=\d)(?=[A-Z][a-z])", " ", value or "")
    return sync_search_api.re.sub(r"\s+", " ", text).strip()


def query_tokens(query):
    return [fold_text(token.strip()) for token in query.split() if len(token.strip()) >= 2]


def matching_positions(raw, tokens):
    if not tokens:
        return [0]
    folded = fold_text(raw)
    primary = tokens[0]
    positions = []
    cursor = 0
    while True:
        position = folded.find(primary, cursor)
        if position < 0:
            break
        window = folded[max(0, position - 40) : position + 260]
        if all(token in window for token in tokens):
            positions.append(position)
        cursor = position + max(1, len(primary))
    return positions


def matched_pdf_fragments(raw, query, country):
    tokens = query_tokens(query)
    if tokens and not all(token in fold_text(raw) for token in tokens):
        return []

    fragments = []
    for position in matching_positions(raw, tokens):
        after_limit = min(len(raw), position + 320)
        for match in PRICE_TOKEN_RE.finditer(raw, position, after_limit):
            fragment = raw[position : match.end()]
            price_text, price_value, currency = sync_search_api.parse_price_v2(fragment, country, require_edge=True)
            if price_value is not None:
                fragments.append((clean_fragment(fragment), price_text, price_value, currency))
                break
        else:
            before_start = max(0, position - 90)
            before_matches = list(PRICE_TOKEN_RE.finditer(raw, before_start, position))
            for match in reversed(before_matches):
                fragment = raw[match.start() : min(len(raw), position + 220)]
                price_text, price_value, currency = sync_search_api.parse_price_v2(fragment, country, require_edge=False)
                if price_value is not None:
                    fragments.append((clean_fragment(fragment), price_text, price_value, currency))
                    break
            else:
                fragment = raw[max(0, position - 40) : min(len(raw), position + 220)]
                price_text, price_value, currency = sync_search_api.parse_price_v2(fragment, country, require_edge=True)
                fragments.append((clean_fragment(fragment), price_text, price_value, currency))

    unique = []
    seen = set()
    for fragment in fragments:
        key = (fragment[0], fragment[1])
        if key not in seen:
            seen.add(key)
            unique.append(fragment)
    return unique


def is_probable_pdf_wine_row(line, has_price=False):
    return (
        has_price
        or sync_search_api.re.search(r"^(?:NV|MV|N/V|\d{4})\b", line, sync_search_api.re.I)
        or (line.count(",") >= 2 and len(line) <= 180)
    )


def match_pdf_lines(text, query, country, limit=200):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    matches = []
    for index, line in enumerate(lines):
        for fragment_index, (fragment, price_text, price_value, currency) in enumerate(matched_pdf_fragments(line, query, country)):
            if not is_probable_pdf_wine_row(fragment, price_value is not None):
                continue
            vintage_match = sync_search_api.re.search(r"\b(19|20)\d{2}\b", fragment)
            matches.append(
                {
                    "id": f"pdf-{index}-{fragment_index}",
                    "text": fragment,
                    "vintage": vintage_match.group(0) if vintage_match else None,
                    "priceValue": price_value,
                    "currency": currency,
                    "prices": [price_text] if price_text else [],
                    "pageNumber": None,
                    "review": price_value is None,
                }
            )
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break
    return matches


def extract_remote_pdf_text(file_url):
    if not file_url:
        return ""
    drive_match = sync_search_api.re.search(r"drive\.google\.com/file/d/([^/]+)", file_url)
    if drive_match:
        file_url = f"https://drive.google.com/uc?export=download&id={drive_match.group(1)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "application/pdf,*/*",
        "Referer": "https://starwinelist.com/",
    }
    with urlopen(Request(file_url, headers=headers), timeout=45) as response:
        body = response.read()
    if not body.startswith(b"%PDF"):
        return ""
    reader = sync_search_api.PdfReader(io.BytesIO(body))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def pdf_lines(params):
    ensure_db()
    wine_list_id = params.get("wineListId", [""])[0]
    query = (params.get("q", [""])[0] or "").strip()
    file_url = (params.get("fileUrl", [""])[0] or "").strip()
    fallback_urls = [
        url.strip()
        for url in (params.get("fallbackUrls", [""])[0] or "").split("|")
        if url.strip()
    ]
    if not wine_list_id:
        return {"status": "review", "reason": "Missing wine list id", "lines": []}
    with connect() as con:
        row = con.execute(
            """
            select
              wl.id,
              wl.text_file_path as textFilePath,
              wl.local_file_path as localFilePath,
              wl.last_error as lastError,
              c.name as country
            from wine_lists wl
            join venues v on v.id = wl.venue_id
            join countries c on c.id = v.country_id
            where wl.id = ? or wl.starwine_list_id = ?
            limit 1
            """,
            (wine_list_id, wine_list_id),
        ).fetchone()
    if not row:
        return {"status": "review", "reason": "Wine list not found", "lines": []}
    item = row_to_dict(row)
    text = ""
    text_path = item.get("textFilePath")
    if text_path:
        path = (ROOT / text_path).resolve()
        if path.exists() and path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
    if not text and item.get("localFilePath"):
        pdf_path = (ROOT / item["localFilePath"]).resolve()
        if pdf_path.exists() and pdf_path.is_file():
            text = sync_search_api.extract_pdf_text(pdf_path)
    if text.strip():
        lines = match_pdf_lines(text, query, item.get("country") or "")
        if lines:
            return {"status": "ok", "reason": "", "lines": lines}
    remote_errors = []
    for remote_url in [file_url, *fallback_urls]:
        if not remote_url:
            continue
        try:
            text = extract_remote_pdf_text(remote_url)
            lines = match_pdf_lines(text, query, item.get("country") or "")
            if lines:
                return {"status": "ok", "reason": "", "lines": lines}
        except Exception as exc:
            remote_errors.append(str(exc))
    if not text.strip():
        return {
            "status": "review",
            "reason": item.get("lastError") or "PDF text extraction returned no text. OCR review required.",
            "lines": [],
        }
    return {
        "status": "review",
        "reason": "No matching text found in extracted PDF text." + (f" {' '.join(dict.fromkeys(remote_errors))}" if remote_errors else ""),
        "lines": [],
    }


def refresh_from_search_api(query, pages=2, max_pdfs=3, page_cap=50):
    sync_search_api.init_db()
    source_ids = []
    entries = 0
    pdfs = 0
    pdf_counter = [0]
    requested_all = pages == "all"
    max_pages = page_cap if requested_all else int(pages)
    last_page = None
    with sync_search_api.connect() as con:
        for page in range(1, max_pages + 1):
            payload, page_entries, page_pdfs = sync_search_api.sync_page(
                con,
                page,
                query,
                "",
                True,
                max_pdfs,
                pdf_counter,
            )
            con.commit()
            entries += page_entries
            pdfs += page_pdfs
            meta = payload.get("meta") or {}
            last_page = int(meta.get("last_page") or page)
            source_ids.extend(
                str(item.get("item_id"))
                for item in payload.get("data", [])
                if item.get("item_type") == "wine_list_line" and item.get("item_id")
            )
            if page >= last_page:
                break
            if requested_all:
                sync_search_api.time.sleep(0.15)
    return {
        "query": query,
        "pages": max_pages if requested_all else int(pages),
        "lastPage": last_page,
        "complete": bool(last_page and max_pages >= last_page),
        "pageCap": page_cap,
        "entries": entries,
        "pdfs": pdfs,
        "sourceItemIds": list(dict.fromkeys(source_ids)),
    }


def unparsed(params):
    ensure_db()
    limit = min(int(params.get("limit", ["200"])[0] or 200), 1000)
    with connect() as con:
        list_rows = con.execute(
            """
            select
              wl.id,
              'list' as kind,
              wl.label,
              null as rawText,
              null as priceText,
              wl.download_url as downloadUrl,
              wl.file_url as fileUrl,
              wl.file_view_url as fileViewUrl,
              wl.local_file_path as localFilePath,
              wl.updated_date as updatedDate,
              wl.entry_count as entryCount,
              wl.last_error as lastError,
              v.name as venueName,
              v.city,
              v.venue_url as venueUrl,
              c.name as country
            from wine_lists wl
            join venues v on v.id = wl.venue_id
            join countries c on c.id = v.country_id
            where wl.entry_count = 0 or wl.local_file_path is null or wl.last_error is not null
            order by wl.updated_date desc, v.name asc
            limit ?
            """,
            (max(1, limit // 2),),
        ).fetchall()
        price_rows = con.execute(
            """
            select
              e.id,
              'price' as kind,
              wl.label,
              e.raw_text as rawText,
              e.price_text as priceText,
              wl.download_url as downloadUrl,
              wl.file_url as fileUrl,
              wl.file_view_url as fileViewUrl,
              wl.local_file_path as localFilePath,
              wl.updated_date as updatedDate,
              wl.entry_count as entryCount,
              'Price needs review' as lastError,
              v.name as venueName,
              v.city,
              v.venue_url as venueUrl,
              c.name as country
            from wine_entries e
            join wine_lists wl on wl.id = e.wine_list_id
            join venues v on v.id = e.venue_id
            join countries c on c.id = v.country_id
            where e.price_value is null or e.price_value <= 0 or e.price_text is null or e.price_text = ''
            order by wl.updated_date desc, v.name asc, e.id asc
            limit ?
            """,
            (limit,),
        ).fetchall()
    items = []
    for row in list(list_rows) + list(price_rows):
        item = row_to_dict(row)
        item["localFileUrl"] = f"/files/{item['localFilePath']}" if item.get("localFilePath") else ""
        items.append(item)
    return {
        "count": len(items),
        "items": items[:limit],
        "listReviewCount": len(list_rows),
        "priceReviewCount": len(price_rows),
    }


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("access-control-allow-origin", ALLOWED_ORIGIN)
        self.send_header("access-control-allow-headers", "content-type, x-whereiskelley-token")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-private-network", "true")
        self.end_headers()

    def api_authorized(self, params):
        if not API_TOKEN:
            return True
        header_token = self.headers.get("x-whereiskelley-token", "").strip()
        query_token = params.get("token", [""])[0].strip()
        return header_token == API_TOKEN or query_token == API_TOKEN

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/health":
                return json_response(
                    self,
                    {
                        "ok": True,
                        "service": "whereiskelley-local-api",
                        "database": DB_PATH.exists(),
                        "authRequired": bool(API_TOKEN),
                    },
                )
            if parsed.path == "/api/guide-collection":
                return json_response(self, guide_collection_status())
            if parsed.path.startswith("/api/") and not self.api_authorized(params):
                return json_response(self, {"error": "Unauthorized"}, status=401)
            if parsed.path == "/api/stats":
                return json_response(self, stats())
            if parsed.path == "/api/guide-watch":
                return json_response(self, guide_watch(params))
            if parsed.path == "/api/filters":
                return json_response(self, filters())
            if parsed.path == "/api/search":
                return json_response(self, search(params))
            if parsed.path == "/api/search_v2":
                return json_response(self, search(params))
            if parsed.path == "/api/pdf-lines":
                return json_response(self, pdf_lines(params))
            if parsed.path == "/api/pdf_lines_v2":
                return json_response(self, pdf_lines(params))
            if parsed.path == "/api/unparsed":
                return json_response(self, unparsed(params))
            if parsed.path in ("/config.js", "/api/config"):
                return javascript_response(self, config_js())
            if parsed.path.startswith("/files/"):
                return self.serve_data_file(parsed.path.removeprefix("/files/"))
            return self.serve_static(parsed.path)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, status=500)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("content-length") or 0)
            raw_body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return json_response(self, {"ok": False, "error": "Invalid JSON body."}, status=400)
            if parsed.path in ("/api/guide-collection", "/api/guide-collection/run"):
                result, status = start_wine_collection(payload if isinstance(payload, dict) else {})
                return json_response(self, result, status=status)
            return json_response(self, {"ok": False, "error": "Not found."}, status=404)
        except Exception as exc:
            return json_response(self, {"ok": False, "error": str(exc)}, status=500)

    def serve_static(self, request_path):
        safe = "index.html" if request_path == "/" else request_path.lstrip("/")
        file_path = (PUBLIC_DIR / safe).resolve()
        if not str(file_path).startswith(str(PUBLIC_DIR.resolve())):
            return text_response(self, "Forbidden", status=403)
        if not file_path.exists() or not file_path.is_file():
            return text_response(self, "Not found", status=404)
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_data_file(self, relative_path):
        file_path = (ROOT / relative_path).resolve()
        data_root = (ROOT / "data").resolve()
        if not str(file_path).startswith(str(data_root)):
            return text_response(self, "Forbidden", status=403)
        if not file_path.exists() or not file_path.is_file():
            return text_response(self, "Not found", status=404)
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", mimetypes.guess_type(file_path.name)[0] or "application/pdf")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    display_host = "localhost" if HOST in ("127.0.0.1", "localhost") else HOST
    print(f"Where is Kelley local server: http://{display_host}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
