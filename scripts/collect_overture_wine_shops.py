#!/usr/bin/env python3
"""Import global wine-shop candidates from Overture Places into SQLite.

This phase discovers businesses only. It never calls Google and never marks a
shop as having a verified wine inventory. Website crawling and product parsing
remain separate, repeatable phases linked through the canonical merchant id.
"""

import argparse
import hashlib
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wine_shop_db import connect_shop, ensure_shop_db  # noqa: E402


DEFAULT_RELEASE = "2026-07-22.0"
STAC_URLS = (
    "https://stac.overturemaps.org/catalog.json",
    "https://stac.overturemaps.org/",
)
RELEASE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}\.\d+)\b")
CATEGORY_RE = re.compile(
    r"(?:^|[^a-z0-9_])(?:beer_wine_and_spirits|bottle_shop|liquor_store|"
    r"wine_and_spirits_store|wine_shop|wine_store)(?:$|[^a-z0-9_])",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"\b(?:wine|wines|fine\s+wines?|winehouse|cellars?|liquor|spirits|"
    r"caviste|vin|vins|vino|vini|vinoteca|enoteca|wein|weinhandlung|wijn|"
    r"vinho|vinhos|garrafeira|vinhandel|wino)\b|"
    r"\u8461\u8404\u9152|\u7d05\u9152|\u7ea2\u9152|\u6d0b\u9152|"
    r"\u30ef\u30a4\u30f3|\uc640\uc778|\u0432\u0438\u043d\u043e",
    re.IGNORECASE,
)
NON_RETAIL_RE = re.compile(
    r"(?:^|[^a-z0-9_])(?:bar|pub|restaurant|winery|vineyard|hotel|lounge)"
    r"(?:$|[^a-z0-9_])",
    re.IGNORECASE,
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fold_text(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_url(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = "https://" + value.lstrip("/")
    parsed = urlparse(value)
    if not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or ""
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), path=path, fragment="").geturl()


def website_domain(value):
    host = urlparse(normalize_url(value)).netloc.casefold()
    return host[4:] if host.startswith("www.") else host


def stable_hash(payload):
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8", errors="ignore")).hexdigest()


def parse_json(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def json_values(value):
    parsed = parse_json(value, [])
    if not isinstance(parsed, list):
        parsed = [parsed]
    values = []
    for item in parsed:
        if isinstance(item, str):
            candidate = item
        elif isinstance(item, dict):
            candidate = item.get("value") or item.get("url") or item.get("website") or ""
        else:
            candidate = ""
        candidate = str(candidate or "").strip()
        if candidate and candidate not in values:
            values.append(candidate)
    return values


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def release_sort_key(value):
    date_part, revision = value.split(".", 1)
    return date_part, int(revision)


def latest_release(fallback=DEFAULT_RELEASE):
    configured = os.environ.get("OVERTURE_RELEASE", "").strip()
    if configured:
        return configured
    found = set()
    for url in STAC_URLS:
        try:
            request = Request(url, headers={"User-Agent": "whereiskelley-overture-import/1.0"})
            with urlopen(request, timeout=15) as response:
                text = response.read(2_000_000).decode("utf-8", errors="ignore")
            found.update(RELEASE_RE.findall(text))
        except Exception:
            continue
    return max(found, key=release_sort_key) if found else fallback


def sql_literal(value):
    return "'{}'".format(str(value).replace("'", "''"))


def load_httpfs(connection):
    try:
        connection.execute("LOAD httpfs")
    except Exception:
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
    connection.execute("SET s3_region='us-west-2'")


def parquet_columns(connection, path):
    result = connection.execute(
        "DESCRIBE SELECT * FROM read_parquet({}) LIMIT 0".format(sql_literal(path))
    )
    return {str(row[0]) for row in result.fetchall()}


def parquet_files(connection, path):
    return [str(row[0]) for row in connection.execute("select file from glob(?)", [path]).fetchall()]


def worker_memory_limit(total_limit, workers):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(GB|MB)\s*", str(total_limit or ""), re.IGNORECASE)
    if not match:
        return ""
    total_mb = float(match.group(1)) * (1024 if match.group(2).upper() == "GB" else 1)
    return "{}MB".format(max(512, int(total_mb / max(1, workers))))


def configure_duck(connection, threads=1, memory_limit=""):
    connection.execute("PRAGMA threads={}".format(max(1, int(threads))))
    connection.execute("SET preserve_insertion_order=false")
    if memory_limit:
        connection.execute("SET memory_limit={}".format(sql_literal(memory_limit)))
    load_httpfs(connection)


def put_worker_message(output, stop_event, message):
    while not stop_event.is_set():
        try:
            output.put(message, timeout=0.5)
            return True
        except queue.Full:
            continue
    return False


def read_overture_file(
    duckdb_module,
    file_path,
    columns,
    country,
    bbox,
    batch_size,
    output,
    stop_event,
    memory_limit,
):
    connection = None
    try:
        connection = duckdb_module.connect()
        configure_duck(connection, threads=1, memory_limit=memory_limit)
        result = connection.execute(build_query(file_path, columns, country, bbox, 0))
        names = [column[0] for column in result.description]
        while not stop_event.is_set():
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            if not put_worker_message(output, stop_event, ("batch", file_path, names, rows)):
                return
        put_worker_message(output, stop_event, ("done", file_path, None, None))
    except Exception as error:
        put_worker_message(output, stop_event, ("error", file_path, None, error))
    finally:
        if connection is not None:
            connection.close()


def build_query(path, columns, country="", bbox=None, limit=0):
    has = columns.__contains__
    name_expr = "names.primary" if has("names") else "''"
    category_parts = []
    select_parts = [
        "id",
        "{} AS name".format(name_expr),
        "confidence" if has("confidence") else "NULL AS confidence",
        "operating_status" if has("operating_status") else "NULL AS operating_status",
        "CAST(update_time AS VARCHAR) AS source_updated_at" if has("update_time") else "NULL AS source_updated_at",
    ]
    if has("categories"):
        select_parts.extend([
            "categories.primary AS old_primary",
            "CAST(to_json(categories) AS VARCHAR) AS categories_json",
        ])
        category_parts.append("CAST(categories AS VARCHAR)")
    else:
        select_parts.extend(["NULL AS old_primary", "NULL AS categories_json"])
    if has("basic_category"):
        select_parts.append("basic_category")
        category_parts.append("basic_category")
    else:
        select_parts.append("NULL AS basic_category")
    if has("taxonomy"):
        select_parts.extend([
            "taxonomy.primary AS taxonomy_primary",
            "CAST(to_json(taxonomy) AS VARCHAR) AS taxonomy_json",
        ])
        category_parts.append("CAST(taxonomy AS VARCHAR)")
    else:
        select_parts.extend(["NULL AS taxonomy_primary", "NULL AS taxonomy_json"])
    if has("websites"):
        select_parts.append("CAST(to_json(websites) AS VARCHAR) AS websites_json")
    else:
        select_parts.append("'[]' AS websites_json")
    if has("phones"):
        select_parts.append("CAST(to_json(phones) AS VARCHAR) AS phones_json")
    else:
        select_parts.append("'[]' AS phones_json")
    if has("socials"):
        select_parts.append("CAST(to_json(socials) AS VARCHAR) AS socials_json")
    else:
        select_parts.append("'[]' AS socials_json")
    if has("addresses"):
        select_parts.extend([
            "addresses[1].freeform AS freeform",
            "addresses[1].locality AS locality",
            "addresses[1].postcode AS postcode",
            "addresses[1].region AS region",
            "addresses[1].country AS country_code",
        ])
        country_expr = "upper(COALESCE(addresses[1].country, ''))"
    else:
        select_parts.extend([
            "NULL AS freeform", "NULL AS locality", "NULL AS postcode",
            "NULL AS region", "NULL AS country_code",
        ])
        country_expr = "''"
    if has("bbox"):
        select_parts.extend(["bbox.xmin AS longitude", "bbox.ymin AS latitude"])
    else:
        select_parts.extend(["NULL AS longitude", "NULL AS latitude"])

    category_expr = "lower(CONCAT_WS(' ', {}))".format(", ".join(category_parts or ["''"]))
    name_search = (
        r"(^|[^a-z])(wine|wines|cellar|cellars|liquor|spirits|caviste|vin|vins|vino|vini|"
        r"vinoteca|enoteca|wein|weinhandlung|wijn|vinho|vinhos|garrafeira|vinhandel|wino)"
        r"([^a-z]|$)|葡萄酒|紅酒|红酒|洋酒|ワイン|와인|вино"
    )
    strict_categories = (
        r"liquor_store|wine_shop|wine_store|wine_and_spirits_store|"
        r"beer_wine_and_spirits|bottle_shop"
    )
    where = [
        "COALESCE(operating_status, 'open') NOT IN ('closed_permanently', 'closed_temporarily')"
        if has("operating_status") else "TRUE",
        "(regexp_matches({}, {}) OR (regexp_matches(lower(COALESCE({}, '')), {}) "
        "AND NOT regexp_matches({}, '(^|[^a-z])(restaurant|bar|pub|winery|vineyard|hotel|lounge)([^a-z]|$)')))".format(
            category_expr,
            sql_literal(strict_categories),
            name_expr,
            sql_literal(name_search),
            category_expr,
        ),
    ]
    if country:
        where.append("{} = {}".format(country_expr, sql_literal(country.upper())))
    if bbox and has("bbox"):
        west, south, east, north = bbox
        where.extend([
            "bbox.xmin BETWEEN {} AND {}".format(float(west), float(east)),
            "bbox.ymin BETWEEN {} AND {}".format(float(south), float(north)),
        ])
    query = "SELECT\n  {}\nFROM read_parquet({})\nWHERE\n  {}".format(
        ",\n  ".join(select_parts), sql_literal(path), "\n  AND ".join(where)
    )
    if limit:
        query += "\nLIMIT {}".format(int(limit))
    return query


def candidate_from_row(row):
    category_text = " ".join(
        str(row.get(key) or "")
        for key in ("old_primary", "categories_json", "basic_category", "taxonomy_primary", "taxonomy_json")
    )
    category_match = bool(CATEGORY_RE.search(category_text))
    name_match = bool(NAME_RE.search(str(row.get("name") or "")))
    if not category_match and (not name_match or NON_RETAIL_RE.search(category_text)):
        return None
    websites = [normalize_url(value) for value in json_values(row.get("websites_json"))]
    websites = [value for value in websites if value]
    country_code = str(row.get("country_code") or "").upper()
    address = str(row.get("freeform") or "").strip()
    if not address:
        address = ", ".join(
            str(row.get(key) or "").strip()
            for key in ("locality", "region", "postcode", "country_code")
            if str(row.get(key) or "").strip()
        )
    payload = {
        "provider_place_id": str(row.get("id") or ""),
        "name": str(row.get("name") or "").strip(),
        "candidate_reason": "retail_category" if category_match else "retail_name",
        "primary_category": row.get("taxonomy_primary") or row.get("basic_category") or row.get("old_primary"),
        "categories": parse_json(row.get("categories_json"), {}),
        "taxonomy": parse_json(row.get("taxonomy_json"), {}),
        "confidence": row.get("confidence"),
        "operating_status": row.get("operating_status"),
        "country_code": country_code,
        "region": row.get("region"),
        "city": row.get("locality"),
        "postcode": row.get("postcode"),
        "address": address,
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "websites": websites,
        "phones": parse_json(row.get("phones_json"), []),
        "socials": parse_json(row.get("socials_json"), []),
        "source_updated_at": row.get("source_updated_at"),
    }
    if not payload["provider_place_id"] or not payload["name"]:
        return None
    payload["raw_hash"] = stable_hash(payload)
    return payload


def prepare_import_connection(con):
    """Give the long-running bulk importer a large local read cache."""
    con.execute("pragma cache_size=-524288")
    con.execute("pragma mmap_size=8589934592")
    con.execute("pragma temp_store=memory")
    con.execute("pragma wal_autocheckpoint=10000")


def load_import_state(con):
    """Cache stable lookup keys so the import does not re-query SQLite per row."""
    places = {
        str(row[0]): (int(row[1]), int(row[2]), str(row[3] or ""))
        for row in con.execute(
            """
            select provider_place_id,id,merchant_id,raw_hash
            from merchant_place_sources
            where provider='overture'
            """
        )
    }
    domains = {}
    for row in con.execute(
        """
        select id,normalized_name,website_domain
        from merchants
        where coalesce(normalized_name,'')!='' and coalesce(website_domain,'')!=''
        order by id
        """
    ):
        domains.setdefault((str(row[1]), str(row[2]).casefold()), int(row[0]))
    return {"places": places, "domains": domains}


def find_existing_merchant(con, candidate, state=None):
    normalized_name = fold_text(candidate["name"])
    website = (candidate.get("websites") or [""])[0]
    domain = website_domain(website)
    if domain:
        if state is not None:
            merchant_id = state["domains"].get((normalized_name, domain))
            if merchant_id is not None:
                return merchant_id
        row = con.execute(
            "select id from merchants where normalized_name=? and website_domain=? limit 1",
            (normalized_name, domain),
        ).fetchone()
        if row:
            return int(row[0])
    lat, lng = candidate.get("latitude"), candidate.get("longitude")
    if lat is not None and lng is not None:
        row = con.execute(
            """
            select id from merchants
            where normalized_name=? and latitude between ? and ? and longitude between ? and ?
            order by abs(latitude-?) + abs(longitude-?) limit 1
            """,
            (normalized_name, float(lat) - 0.003, float(lat) + 0.003,
             float(lng) - 0.003, float(lng) + 0.003, float(lat), float(lng)),
        ).fetchone()
        if row:
            return int(row[0])
    return None


def create_merchant(con, candidate, now):
    website = (candidate.get("websites") or [""])[0]
    return con.execute(
        """
        insert into merchants(
          name, normalized_name, merchant_type, website_url, website_domain,
          country, city, address, latitude, longitude, phone, profile_status,
          first_seen_at, last_seen_at, inventory_status, active, raw_hash
        ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending', 1, ?)
        """,
        (
            candidate["name"], fold_text(candidate["name"]), "Wine Shop",
            website or None, website_domain(website) or None,
            candidate.get("country_code") or None, candidate.get("city") or None,
            candidate.get("address") or None, candidate.get("latitude"), candidate.get("longitude"),
            (json_values(candidate.get("phones")) or [None])[0], "discovered", now, now,
            candidate["raw_hash"],
        ),
    ).lastrowid


def update_merchant(con, merchant_id, candidate, now):
    website = (candidate.get("websites") or [""])[0]
    con.execute(
        """
        update merchants set
          website_url=case when coalesce(website_url,'')='' then ? else website_url end,
          website_domain=case when coalesce(website_domain,'')='' then ? else website_domain end,
          country=case when coalesce(country,'')='' then ? else country end,
          city=case when coalesce(city,'')='' then ? else city end,
          address=case when coalesce(address,'')='' then ? else address end,
          latitude=coalesce(latitude, ?), longitude=coalesce(longitude, ?),
          phone=case when coalesce(phone,'')='' then ? else phone end,
          last_seen_at=?, active=1
        where id=?
        """,
        (
            website or None, website_domain(website) or None,
            candidate.get("country_code") or None, candidate.get("city") or None,
            candidate.get("address") or None, candidate.get("latitude"), candidate.get("longitude"),
            (json_values(candidate.get("phones")) or [None])[0], now, merchant_id,
        ),
    )


def upsert_candidate(con, candidate, run_id, release, now=None, state=None):
    now = now or utc_now()
    cached_previous = state["places"].get(candidate["provider_place_id"]) if state is not None else None
    previous = cached_previous or con.execute(
        "select id, merchant_id, raw_hash from merchant_place_sources where provider='overture' and provider_place_id=?",
        (candidate["provider_place_id"],),
    ).fetchone()
    if previous:
        if isinstance(previous, tuple):
            place_source_id, merchant_id, previous_hash = previous
        else:
            place_source_id = int(previous["id"])
            merchant_id = int(previous["merchant_id"])
            previous_hash = str(previous["raw_hash"] or "")
        outcome = "unchanged" if previous_hash == candidate["raw_hash"] else "updated"
    else:
        merchant_id = find_existing_merchant(con, candidate, state=state)
        if merchant_id is None:
            merchant_id = create_merchant(con, candidate, now)
        place_source_id = None
        outcome = "inserted"
    update_merchant(con, merchant_id, candidate, now)
    website = (candidate.get("websites") or [""])[0]
    domain = website_domain(website)
    if state is not None and domain:
        state["domains"].setdefault((fold_text(candidate["name"]), domain), merchant_id)

    if outcome == "unchanged":
        con.execute(
            """
            update merchant_place_sources set
              provider_release=?,last_seen_at=?,last_seen_run_id=?,active=1
            where id=?
            """,
            (release, now, run_id, place_source_id),
        )
        con.execute(
            "update merchant_websites set active=1,last_seen_at=? where place_source_id=?",
            (now, place_source_id),
        )
        if state is not None:
            state["places"][candidate["provider_place_id"]] = (
                place_source_id, merchant_id, candidate["raw_hash"]
            )
        return outcome

    categories_json = json.dumps(
        {"categories": candidate.get("categories") or {}, "taxonomy": candidate.get("taxonomy") or {}},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    values = (
        merchant_id, "overture", candidate["provider_place_id"], release,
        candidate.get("candidate_reason"), candidate["name"], fold_text(candidate["name"]),
        candidate.get("primary_category"), categories_json, candidate.get("confidence"),
        candidate.get("operating_status"), candidate.get("country_code"), candidate.get("country_code"),
        candidate.get("region"), candidate.get("city"), candidate.get("postcode"), candidate.get("address"),
        candidate.get("latitude"), candidate.get("longitude"),
        json.dumps(candidate.get("websites") or [], ensure_ascii=False),
        json.dumps(candidate.get("phones") or [], ensure_ascii=False),
        json.dumps(candidate.get("socials") or [], ensure_ascii=False),
        candidate.get("source_updated_at"), candidate["raw_hash"], now, now, run_id, run_id,
    )
    source_sql = """
        insert into merchant_place_sources(
          merchant_id,provider,provider_place_id,provider_release,candidate_reason,name,normalized_name,
          primary_category,categories_json,confidence,operating_status,country_code,country,region,city,
          postcode,address,latitude,longitude,websites_json,phones_json,socials_json,source_updated_at,
          raw_hash,first_seen_at,last_seen_at,first_seen_run_id,last_seen_run_id,active
        ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        on conflict(provider,provider_place_id) do update set
          merchant_id=excluded.merchant_id,provider_release=excluded.provider_release,
          candidate_reason=excluded.candidate_reason,name=excluded.name,normalized_name=excluded.normalized_name,
          primary_category=excluded.primary_category,categories_json=excluded.categories_json,
          confidence=excluded.confidence,operating_status=excluded.operating_status,
          country_code=excluded.country_code,country=excluded.country,region=excluded.region,city=excluded.city,
          postcode=excluded.postcode,address=excluded.address,latitude=excluded.latitude,
          longitude=excluded.longitude,websites_json=excluded.websites_json,phones_json=excluded.phones_json,
          socials_json=excluded.socials_json,source_updated_at=excluded.source_updated_at,
          raw_hash=excluded.raw_hash,last_seen_at=excluded.last_seen_at,
          last_seen_run_id=excluded.last_seen_run_id,active=1
        """
    cursor = con.execute(source_sql, values)
    if place_source_id is None:
        place_source_id = int(cursor.lastrowid)
    con.execute("update merchant_websites set active=0 where place_source_id=?", (place_source_id,))
    for website in candidate.get("websites") or []:
        normalized = normalize_url(website)
        if not normalized:
            continue
        con.execute(
            """
            insert into merchant_websites(
              merchant_id,place_source_id,url,normalized_url,domain,role,provider,status,
              first_seen_at,last_seen_at,active
            ) values(?,?,?,?,?,'official_candidate','overture','unverified',?,?,1)
            on conflict(merchant_id,normalized_url) do update set
              place_source_id=excluded.place_source_id,url=excluded.url,domain=excluded.domain,
              last_seen_at=excluded.last_seen_at,active=1
            """,
            (merchant_id, place_source_id, website, normalized, website_domain(normalized), now, now),
        )
    if state is not None:
        state["places"][candidate["provider_place_id"]] = (
            place_source_id, merchant_id, candidate["raw_hash"]
        )
    return outcome


def upsert_candidate_batch(con, candidates, run_id, release, now=None, state=None):
    """Merge one fetched batch, collapsing unchanged rows into three SQL updates."""
    now = now or utc_now()
    outcomes = {"inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}
    unchanged = []
    for candidate in candidates:
        previous = state["places"].get(candidate["provider_place_id"]) if state is not None else None
        if previous and previous[2] == candidate["raw_hash"]:
            unchanged.append((int(previous[0]), int(previous[1])))
            continue
        try:
            outcome = upsert_candidate(
                con, candidate, run_id, release, now=now, state=state
            )
            outcomes[outcome] += 1
        except (sqlite3.Error, ValueError, TypeError):
            outcomes["errors"] += 1

    if unchanged:
        con.execute(
            """
            create temp table if not exists overture_unchanged_batch(
              place_source_id integer primary key,
              merchant_id integer not null
            ) without rowid
            """
        )
        con.execute("delete from overture_unchanged_batch")
        con.executemany(
            "insert into overture_unchanged_batch(place_source_id,merchant_id) values(?,?)",
            unchanged,
        )
        con.execute(
            """
            update merchants set last_seen_at=?,active=1
            where id in (select merchant_id from overture_unchanged_batch)
            """,
            (now,),
        )
        con.execute(
            """
            update merchant_place_sources set
              provider_release=?,last_seen_at=?,last_seen_run_id=?,active=1
            where id in (select place_source_id from overture_unchanged_batch)
            """,
            (release, now, run_id),
        )
        con.execute(
            """
            update merchant_websites set active=1,last_seen_at=?
            where place_source_id in (select place_source_id from overture_unchanged_batch)
            """,
            (now,),
        )
        outcomes["unchanged"] += len(unchanged)
    return outcomes


def finalize_full_run(con, run_id, now=None):
    now = now or utc_now()
    stale_ids = [
        row[0] for row in con.execute(
            "select id from merchant_place_sources where provider='overture' and active=1 and last_seen_run_id<>?",
            (run_id,),
        ).fetchall()
    ]
    if stale_ids:
        placeholders = ",".join("?" for _ in stale_ids)
        con.execute(
            "update merchant_place_sources set active=0,last_seen_at=? where id in ({})".format(placeholders),
            [now] + stale_ids,
        )
        con.execute(
            "update merchant_websites set active=0 where place_source_id in ({})".format(placeholders),
            stale_ids,
        )
    con.execute(
        """
        update merchants set active=0
        where wine_searcher_id is null
          and not exists(select 1 from merchant_place_sources ps where ps.merchant_id=merchants.id and ps.active=1)
          and not exists(select 1 from merchant_sources ms where ms.merchant_id=merchants.id and ms.status='found')
        """
    )
    return len(stale_ids)


def run_import(args):
    try:
        import duckdb
    except ImportError as error:
        raise SystemExit("DuckDB is required: python -m pip install -r requirements.txt") from error

    release = latest_release() if args.release == "latest" else args.release
    path = "s3://overturemaps-us-west-2/release/{}/theme=places/type=place/*.parquet".format(release)
    scope = "global"
    if args.country:
        scope = "country:{}".format(args.country.upper())
    if args.bbox:
        scope += ";bbox:" + ",".join(str(value) for value in args.bbox)
    partial = bool(args.country or args.bbox or args.limit)
    config = {
        "release": release, "path": path, "scope": scope, "limit": args.limit,
        "batchSize": args.batch_size, "threads": args.threads,
        "sourceWorkers": args.source_workers, "partial": partial,
    }
    ensure_shop_db(args.db)
    con = connect_shop(args.db)
    prepare_import_connection(con)
    run_id = con.execute(
        "insert into merchant_discovery_runs(provider,provider_release,scope,status,config_json) values('overture',?,?, 'running',?)",
        (release, scope, json.dumps(config, ensure_ascii=False)),
    ).lastrowid
    con.commit()
    counts = {"source_rows": 0, "candidates": 0, "inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}
    started_at = utc_now()
    started_monotonic = time.monotonic()
    import_state = load_import_state(con)
    source_files_total = 0
    source_files_completed = 0
    source_workers = 1

    def write_progress(
        status="running",
        message="Reading Overture Places",
        phase="overture_preparing",
        stage_index=1,
        stage_label="Prepare Overture release",
        stage_status="running",
    ):
        elapsed_seconds = max(0.001, time.monotonic() - started_monotonic)
        atomic_write_json(args.progress, {
            "generatedAt": utc_now(), "startedAt": started_at,
            "status": status, "phase": phase,
            "message": message, "runId": run_id, "provider": "overture", "release": release,
            "scope": scope, "threads": args.threads, "memoryLimit": args.memory_limit,
            "batchSize": args.batch_size, "sourceWorkers": source_workers,
            "sourceFiles": source_files_total,
            "sourceFilesCompleted": source_files_completed,
            "elapsedSeconds": round(elapsed_seconds, 1),
            "rowsPerSecond": round(counts["source_rows"] / elapsed_seconds, 1),
            "stageIndex": stage_index, "stageCount": 4,
            "stageLabel": stage_label, "stageStatus": stage_status,
            "stageProcessed": counts["source_rows"] if stage_index == 2 else None,
            "stageTotal": None,
            **counts,
        })

    def merge_rows(names, rows):
        now = utc_now()
        candidates = []
        for values in rows:
            counts["source_rows"] += 1
            candidate = candidate_from_row(dict(zip(names, values)))
            if not candidate:
                continue
            counts["candidates"] += 1
            candidates.append(candidate)
        batch_outcomes = upsert_candidate_batch(
            con, candidates, run_id, release, now=now, state=import_state
        )
        for outcome, value in batch_outcomes.items():
            counts[outcome] += value
        con.execute(
            """
            update merchant_discovery_runs set source_rows=?,candidates=?,inserted=?,updated=?,unchanged=?,errors=?
            where id=?
            """,
            (counts["source_rows"], counts["candidates"], counts["inserted"], counts["updated"],
             counts["unchanged"], counts["errors"], run_id),
        )
        con.commit()
        write_progress(
            message="Read {:,} places and saved {:,} wine-shop candidates.".format(
                counts["source_rows"], counts["candidates"]
            ),
            phase="overture_importing",
            stage_index=2,
            stage_label="Import and merge shop directory",
        )
        print(
            "Saved {:,} candidates ({} new, {} updated, {} unchanged, {} errors)".format(
                counts["candidates"], counts["inserted"], counts["updated"],
                counts["unchanged"], counts["errors"]
            ),
            flush=True,
        )

    write_progress()
    duck = None
    stop_event = threading.Event()
    reader_threads = []
    try:
        duck = duckdb.connect()
        configure_duck(duck, threads=args.threads, memory_limit=args.memory_limit)
        files = parquet_files(duck, path)
        if not files:
            raise RuntimeError("Overture release contains no Places parquet files")
        source_files_total = len(files)
        source_workers = min(args.source_workers, source_files_total)
        columns = parquet_columns(duck, files[0])
        write_progress(
            message="Reading {} Overture files with {} parallel streams.".format(
                source_files_total, source_workers
            ),
            phase="overture_importing",
            stage_index=2,
            stage_label="Import and merge shop directory",
        )
        if args.limit or source_workers == 1:
            result = duck.execute(build_query(path, columns, args.country, args.bbox, args.limit))
            names = [column[0] for column in result.description]
            while True:
                rows = result.fetchmany(args.batch_size)
                if not rows:
                    break
                merge_rows(names, rows)
            source_files_completed = source_files_total
        else:
            duck.close()
            duck = None
            output = queue.Queue(maxsize=source_workers * 2)
            per_worker_memory = worker_memory_limit(args.memory_limit, source_workers)
            for file_path in files:
                thread = threading.Thread(
                    target=read_overture_file,
                    args=(
                        duckdb, file_path, columns, args.country, args.bbox,
                        args.batch_size, output, stop_event, per_worker_memory,
                    ),
                    name="overture-reader-{}".format(len(reader_threads) + 1),
                    daemon=True,
                )
                reader_threads.append(thread)
            next_reader = 0
            active_readers = 0

            def start_reader():
                nonlocal next_reader, active_readers
                if next_reader < len(reader_threads):
                    reader_threads[next_reader].start()
                    next_reader += 1
                    active_readers += 1

            for _ in range(source_workers):
                start_reader()
            while active_readers:
                kind, file_path, names, payload = output.get()
                if kind == "batch":
                    merge_rows(names, payload)
                elif kind == "done":
                    active_readers -= 1
                    source_files_completed += 1
                    start_reader()
                    write_progress(
                        message="Completed {:,}/{:,} Overture files with {} parallel streams.".format(
                            source_files_completed, source_files_total, source_workers
                        ),
                        phase="overture_importing",
                        stage_index=2,
                        stage_label="Import and merge shop directory",
                    )
                else:
                    raise RuntimeError("Failed reading {}: {}".format(file_path, payload))
        write_progress(
            message="Finalizing website URLs and reconciling the previous directory.",
            phase="overture_reconciling",
            stage_index=3,
            stage_label="Finalize website queue",
        )
        deactivated = finalize_full_run(con, run_id) if not partial else 0
        con.execute(
            """
            update merchant_discovery_runs set status='complete',finished_at=?,source_rows=?,candidates=?,
              inserted=?,updated=?,unchanged=?,deactivated=?,errors=? where id=?
            """,
            (utc_now(), counts["source_rows"], counts["candidates"], counts["inserted"],
             counts["updated"], counts["unchanged"], deactivated, counts["errors"], run_id),
        )
        con.commit()
        counts["deactivated"] = deactivated
        write_progress(
            "complete",
            "Wine-shop directory update completed. Website inventory scan is ready.",
            phase="overture_complete",
            stage_index=3,
            stage_label="Finalize website queue",
            stage_status="complete",
        )
        return {"runId": run_id, "startedAt": started_at, "finishedAt": utc_now(), "release": release, **counts}
    except Exception as error:
        con.rollback()
        con.execute(
            "update merchant_discovery_runs set status='failed',finished_at=?,errors=errors+1,error=? where id=?",
            (utc_now(), "{}: {}".format(type(error).__name__, error), run_id),
        )
        con.commit()
        counts["errors"] += 1
        write_progress(
            "failed",
            "Overture import failed: {}".format(error),
            phase="overture_failed",
            stage_index=2,
            stage_label="Import and merge shop directory",
            stage_status="failed",
        )
        raise
    finally:
        stop_event.set()
        for thread in reader_threads:
            if thread.is_alive():
                thread.join(timeout=5)
        if duck is not None:
            duck.close()
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "db" / "wine_shops.sqlite")
    parser.add_argument("--progress", type=Path, default=ROOT / "public" / "data" / "shop-progress.json")
    parser.add_argument("--release", default="latest", help="Overture release or 'latest'")
    parser.add_argument("--country", default="", help="Optional ISO country code for a partial run")
    parser.add_argument("--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--limit", type=int, default=0, help="Testing only; makes the run partial")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--threads", type=int, default=max(1, min(os.cpu_count() or 2, 8)))
    parser.add_argument(
        "--source-workers", type=int, default=0,
        help="Parallel Overture parquet readers; 0 uses twice the CPU thread count",
    )
    parser.add_argument("--memory-limit", default="", help="DuckDB limit such as 12GB")
    args = parser.parse_args()
    args.batch_size = max(100, min(args.batch_size, 10_000))
    args.source_workers = max(1, min(args.source_workers or args.threads * 2, 16))
    summary = run_import(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
