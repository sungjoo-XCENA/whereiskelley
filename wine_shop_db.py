import hashlib
import json
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse


ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "db" / "wine_shops_schema.sql"
PROGRESS_PATH = ROOT / "public" / "data" / "shop-progress.json"


def resolve_shop_db_path():
    configured = os.environ.get("WHEREISKELLEY_SHOP_DB_PATH", "").strip()
    return Path(configured) if configured else ROOT / "db" / "wine_shops.sqlite"


SHOP_DB_PATH = resolve_shop_db_path()
_SCHEMA_LOCK = threading.Lock()
_INITIALIZED_PATHS = set()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fold_text(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def search_tokens(value):
    return [token for token in re.findall(r"[\w]+", fold_text(value)) if len(token) >= 2]


def content_hash(*values):
    joined = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha256(joined.encode("utf-8", errors="ignore")).hexdigest()


def connect_shop(path=None):
    db_path = Path(path or SHOP_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("pragma journal_mode=wal")
    con.execute("pragma synchronous=normal")
    con.execute("pragma foreign_keys=on")
    con.execute("pragma busy_timeout=30000")
    return con


def ensure_shop_db(path=None):
    db_path = str(Path(path or SHOP_DB_PATH).resolve())
    if db_path in _INITIALIZED_PATHS:
        return
    with _SCHEMA_LOCK:
        if db_path in _INITIALIZED_PATHS:
            return
        con = connect_shop(db_path)
        try:
            con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            con.commit()
            _INITIALIZED_PATHS.add(db_path)
        finally:
            con.close()


def read_progress():
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _row_dict(row):
    return {key: row[key] for key in row.keys()}


def shop_collection_status(path=None, map_limit=6000):
    ensure_shop_db(path)
    progress = read_progress()
    con = connect_shop(path)
    try:
        counts = _row_dict(con.execute(
            """
            select
              (select count(*) from merchant_scan_ids) as idsChecked,
              (select count(*) from merchants where active=1) as merchants,
              (select count(*) from merchants where website_url is not null and trim(website_url)!='' and active=1) as withWebsite,
              (select count(*) from merchants where inventory_status='found' and active=1) as inventoryFound,
              (select count(*) from merchants where inventory_status='review' and active=1) as review,
              (select count(*) from merchant_sources where status='found') as sources,
              (select count(*) from merchant_products where active=1) as products,
              (select count(*) from merchant_reviews where status='open') as openReviews,
              (select count(*) from merchant_place_sources where provider='overture' and active=1) as overturePlaces,
              (select count(*) from merchant_websites where provider='overture' and active=1) as overtureWebsites
            """
        ).fetchone())
        latest_runs = [
            _row_dict(row)
            for row in con.execute(
                "select * from merchant_scan_runs order by id desc limit 8"
            ).fetchall()
        ]
        discovery_runs = [
            _row_dict(row)
            for row in con.execute(
                "select * from merchant_discovery_runs order by id desc limit 8"
            ).fetchall()
        ]
        map_merchants = [
            _row_dict(row)
            for row in con.execute(
                """
                select m.id, m.wine_searcher_id as wineSearcherId, m.name, m.merchant_type as merchantType,
                       m.country, m.city, m.address, m.latitude as lat, m.longitude as lng,
                       m.website_url as websiteUrl, m.wine_searcher_url as wineSearcherUrl,
                       m.inventory_status as inventoryStatus, m.last_inventory_checked_at as lastCheckedAt,
                       count(distinct s.id) as sourceCount, count(distinct p.id) as productCount,
                       max(case when s.status='found' then s.source_url else null end) as inventoryUrl
                from merchants m
                left join merchant_sources s on s.merchant_id=m.id
                left join merchant_products p on p.merchant_id=m.id and p.active=1
                where m.active=1 and m.latitude is not null and m.longitude is not null
                group by m.id
                order by m.id
                limit ?
                """,
                (int(map_limit),),
            ).fetchall()
        ]
        return {
            "generatedAt": utc_now(),
            "progress": progress,
            "counts": {key: int(value or 0) for key, value in counts.items()},
            "latestRuns": latest_runs,
            "latestDiscoveryRuns": discovery_runs,
            "mapMerchants": map_merchants,
            "databasePath": str(Path(path or SHOP_DB_PATH)),
        }
    finally:
        con.close()


def search_shop_products(query, country="", city="", vintage="", limit=5000, path=None):
    tokens = search_tokens(query)
    if not tokens:
        return []
    ensure_shop_db(path)
    con = connect_shop(path)
    args = []
    filters = ["p.active=1", "m.active=1"]
    fts_query = " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
    join_fts = "join merchant_products_fts f on f.rowid=p.id"
    filters.append("merchant_products_fts match ?")
    args.append(fts_query)
    if country:
        filters.append("lower(coalesce(m.country,''))=lower(?)")
        args.append(country)
    if city:
        filters.append("lower(coalesce(m.city,'')) like lower(?)")
        args.append(f"%{city}%")
    if vintage:
        filters.append("(p.vintage=? or p.raw_text like ?)")
        args.extend([vintage, f"%{vintage}%"])
    args.append(max(1, min(int(limit), 5000)))
    sql = f"""
      select p.*, m.name as merchant_name, m.merchant_type, m.country, m.city, m.address,
             m.latitude, m.longitude, m.website_url, m.wine_searcher_url,
             s.source_url as inventory_url, s.source_type, s.last_checked_at
      from merchant_products p
      {join_fts}
      join merchants m on m.id=p.merchant_id
      join merchant_sources s on s.id=p.source_id
      where {' and '.join(filters)}
      order by case when p.price_value is null then 1 else 0 end, p.price_value, m.name, p.id
      limit ?
    """
    try:
        rows = con.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        fallback_filters = ["p.active=1", "m.active=1"]
        fallback_args = []
        for token in tokens:
            fallback_filters.append("p.normalized_text like ?")
            fallback_args.append(f"%{token}%")
        if country:
            fallback_filters.append("lower(coalesce(m.country,''))=lower(?)")
            fallback_args.append(country)
        if city:
            fallback_filters.append("lower(coalesce(m.city,'')) like lower(?)")
            fallback_args.append(f"%{city}%")
        if vintage:
            fallback_filters.append("(p.vintage=? or p.raw_text like ?)")
            fallback_args.extend([vintage, f"%{vintage}%"])
        fallback_args.append(max(1, min(int(limit), 5000)))
        rows = con.execute(
            f"""
            select p.*, m.name as merchant_name, m.merchant_type, m.country, m.city, m.address,
                   m.latitude, m.longitude, m.website_url, m.wine_searcher_url,
                   s.source_url as inventory_url, s.source_type, s.last_checked_at
            from merchant_products p
            join merchants m on m.id=p.merchant_id
            join merchant_sources s on s.id=p.source_id
            where {' and '.join(fallback_filters)}
            order by case when p.price_value is null then 1 else 0 end, p.price_value, m.name, p.id
            limit ?
            """,
            fallback_args,
        ).fetchall()
    finally:
        con.close()

    results = []
    for row in rows:
        source_url = row["source_url"] or row["inventory_url"] or row["website_url"] or ""
        location_query = ", ".join(filter(None, (row["merchant_name"], row["address"], row["city"], row["country"])))
        price_text = (row["price_text"] or "").strip()
        results.append({
            "id": f"shop-{row['merchant_id']}-{row['id']}",
            "text": row["raw_text"] or row["raw_name"],
            "producer": row["producer"] or "",
            "wineName": row["wine_name"] or row["raw_name"],
            "vintage": row["vintage"] or "",
            "region": row["region"] or "",
            "priceValue": row["price_value"],
            "currency": row["currency"] or "",
            "prices": [price_text] if price_text else [],
            "source": "Wine Shop Database",
            "availabilityOnly": row["price_value"] is None,
            "availability": row["availability"] or "",
            "venue": {
                "id": f"shop-merchant-{row['merchant_id']}",
                "name": row["merchant_name"],
                "type": row["merchant_type"] or "Wine Shop",
                "city": row["city"] or "",
                "country": row["country"] or "",
                "lat": row["latitude"],
                "lng": row["longitude"],
                "address": row["address"] or "",
                "googleMapsUrl": f"https://www.google.com/maps/search/?api=1&query={quote_plus(location_query)}",
                "url": row["website_url"] or row["wine_searcher_url"] or "",
            },
            "wineList": {
                "id": f"shop-source-{row['source_id']}",
                "label": "Wine shop inventory",
                "downloadUrl": source_url,
                "fileUrl": source_url,
                "updatedDate": row["last_checked_at"] or row["last_seen_at"] or "",
                "availabilityOnly": row["price_value"] is None,
            },
        })
    return results


def upsert_product(con, merchant_id, source_id, item):
    raw_name = str(item.get("raw_name") or item.get("name") or "").strip()
    raw_text = str(item.get("raw_text") or raw_name).strip()
    source_key = str(item.get("source_key") or item.get("source_url") or content_hash(raw_name, raw_text))
    normalized = fold_text(" ".join(filter(None, (
        raw_name,
        item.get("producer"),
        item.get("wine_name"),
        item.get("region"),
        raw_text,
    ))))
    observed_hash = content_hash(
        item.get("price_value"), item.get("currency"), item.get("availability"), raw_text
    )
    con.execute(
        """
        insert into merchant_products(
          merchant_id, source_id, source_key, source_url, raw_name, normalized_text,
          producer, wine_name, vintage, region, size_ml, pack_quantity, price_value,
          currency, price_text, price_krw, availability, raw_text, content_hash,
          active, first_seen_at, last_seen_at
        ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
        on conflict(source_id, source_key) do update set
          source_url=excluded.source_url, raw_name=excluded.raw_name,
          normalized_text=excluded.normalized_text, producer=excluded.producer,
          wine_name=excluded.wine_name, vintage=excluded.vintage, region=excluded.region,
          size_ml=excluded.size_ml, pack_quantity=excluded.pack_quantity,
          price_value=excluded.price_value, currency=excluded.currency,
          price_text=excluded.price_text, price_krw=excluded.price_krw,
          availability=excluded.availability, raw_text=excluded.raw_text,
          content_hash=excluded.content_hash, active=1, last_seen_at=excluded.last_seen_at
        """,
        (
            merchant_id, source_id, source_key, item.get("source_url"), raw_name, normalized,
            item.get("producer"), item.get("wine_name"), item.get("vintage"), item.get("region"),
            item.get("size_ml"), item.get("pack_quantity"), item.get("price_value"),
            item.get("currency"), item.get("price_text"), item.get("price_krw"),
            item.get("availability"), raw_text, observed_hash, utc_now(), utc_now(),
        ),
    )
    product_id = con.execute(
        "select id from merchant_products where source_id=? and source_key=?",
        (source_id, source_key),
    ).fetchone()[0]
    con.execute(
        """
        insert or ignore into merchant_offer_history(
          product_id, observed_at, price_value, currency, availability, content_hash
        ) values(?,?,?,?,?,?)
        """,
        (product_id, utc_now(), item.get("price_value"), item.get("currency"), item.get("availability"), observed_hash),
    )
    return product_id
