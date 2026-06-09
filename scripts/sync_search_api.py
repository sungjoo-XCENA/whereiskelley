import argparse
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "starwine.sqlite"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
DOWNLOAD_DIR = ROOT / "data" / "downloads" / "api"
TEXT_DIR = ROOT / "data" / "text" / "api"
API_URL = "https://starwinelist.com/api/search"
LOCATION_API_URL = "https://starwinelist.com/api/location/search"
LOCATION_CACHE = {}
COUNTRY_COORDS = {
    "Argentina": (-38.4161, -63.6167),
    "Austria": (47.5162, 14.5501),
    "Czech Republic": (49.8175, 15.4730),
    "Denmark": (56.2639, 9.5018),
    "France": (46.2276, 2.2137),
    "Germany": (51.1657, 10.4515),
    "Greater China": (35.8617, 104.1954),
    "Hong Kong": (22.3193, 114.1694),
    "Netherlands": (52.1326, 5.2913),
    "Singapore": (1.3521, 103.8198),
    "Spain": (40.4637, -3.7492),
    "Sweden": (60.1282, 18.6435),
    "UK": (55.3781, -3.4360),
    "USA": (37.0902, -95.7129),
}
CURRENCY_RE = r"\u20ac|\$|\u00a3|\u00a5|\u20a9|CHF|DKK|SEK|NOK|USD|EUR|GBP|CAD|AUD|SGD|HKD|AED|CNY|CZK|ARS|JPY|KRW"
PRICE_CURRENCY_RE = r"A\$|AU\$|CA\$|HK\$|S\$|US\$|" + CURRENCY_RE
NO_PRICE_RE = r"\b(?:ask\s+(?:your\s+)?sommelier|ask\s+(?:us|staff)|on\s+request|upon\s+request|price\s+on\s+request|market\s+price|enquire|inquire|poa|n/?a|sold\s+out)\b|\ubb38\uc758|\uc2dc\uac00|\uc2ef\uac00"
CURRENCY_ALIASES = {
    "\u20ac": "EUR",
    "$": "USD",
    "\u00a3": "GBP",
    "\u00a5": "JPY",
    "\u20a9": "KRW",
}
COUNTRY_CURRENCIES = {
    "Argentina": "ARS",
    "Australia": "AUD",
    "Austria": "EUR",
    "Belgium": "EUR",
    "Canada": "CAD",
    "Czech Republic": "CZK",
    "Denmark": "DKK",
    "France": "EUR",
    "Germany": "EUR",
    "Greater China": "CNY",
    "Hong Kong": "HKD",
    "Italy": "EUR",
    "Netherlands": "EUR",
    "Norway": "NOK",
    "Singapore": "SGD",
    "Spain": "EUR",
    "Sweden": "SEK",
    "Switzerland": "CHF",
    "UK": "GBP",
    "USA": "USD",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(value):
    value = (value or "unknown").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        wine_list_columns = {row[1] for row in con.execute("pragma table_info(wine_lists)").fetchall()}
        if "last_error" not in wine_list_columns:
            con.execute("alter table wine_lists add column last_error text")
        if "file_url" not in wine_list_columns:
            con.execute("alter table wine_lists add column file_url text")
        if "file_view_url" not in wine_list_columns:
            con.execute("alter table wine_lists add column file_view_url text")
        entry_columns = {row[1] for row in con.execute("pragma table_info(wine_entries)").fetchall()}
        if "source_item_id" not in entry_columns:
            con.execute("alter table wine_entries add column source_item_id text")
        venue_columns = {row[1] for row in con.execute("pragma table_info(venues)").fetchall()}
        if "region_slug" not in venue_columns:
            con.execute("alter table venues add column region_slug text")
        if "lat" not in venue_columns:
            con.execute("alter table venues add column lat real")
        if "lng" not in venue_columns:
            con.execute("alter table venues add column lng real")
        con.execute("create unique index if not exists idx_wine_entries_source_item on wine_entries(source_item_id) where source_item_id is not null")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    return con


def fetch_json(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://starwinelist.com/search",
    }
    with urlopen(Request(url, headers=headers), timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_pdf_url(url):
    match = re.search(r"drive\.google\.com/file/d/([^/]+)", url or "")
    if match:
        return f"https://drive.google.com/uc?export=download&id={match.group(1)}"
    return url


def fetch_location(slug):
    if not slug:
        return None
    if slug in LOCATION_CACHE:
        return LOCATION_CACHE[slug]
    try:
        payload = fetch_json(f"{LOCATION_API_URL}?{urlencode({'slug': slug})}")
        location = payload.get("data")
    except Exception:
        location = None
    LOCATION_CACHE[slug] = location
    return location


def fetch_binary(url):
    url = resolve_pdf_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "application/pdf,*/*",
        "Referer": "https://starwinelist.com/search",
    }
    with urlopen(Request(url, headers=headers), timeout=90) as response:
        return response.read(), response.headers.get("content-type", ""), response.url


def country_city_from_result(result):
    item = result.get("item") or {}
    venue = ((item.get("pw") or {}).get("venue") or {})
    city = (result.get("city") or {}).get("name") or (item.get("region") or {}).get("name") or ""
    location = venue.get("location") or result.get("region_breadcrumbs") or ""
    parts = [part.strip() for part in location.split(",") if part.strip()]
    country = parts[-1] if parts else ""
    if parts and (not city or city == country):
        city = parts[0]
    if not country and city:
        country = city
    return country or "Unknown", city


def location_from_result(result, country, city):
    city_obj = result.get("city") or {}
    region = ((result.get("item") or {}).get("region") or {})
    slug = city_obj.get("slug") or (slugify(city) if city and city != country else "") or region.get("slug") or slugify(city)
    location = fetch_location(slug)
    lat = location.get("lat") if location else None
    lng = location.get("lng") if location else None
    star_map_url = ((location or {}).get("urls") or {}).get("map")
    if lat is None or lng is None:
        lat, lng = COUNTRY_COORDS.get(country, (None, None))
    return slug, lat, lng, star_map_url


def venue_slug_from_url(url):
    try:
        return urlparse(url).path.rstrip("/").split("/")[-1] or "unknown"
    except Exception:
        return "unknown"


def parse_price(line):
    numbers = re.findall(r"\b\d{2,6}(?:[.,]\d{2})?\b", line or "")
    candidates = [item for item in numbers if not re.fullmatch(r"(19|20)\d{2}", item)]
    if not candidates:
        return "", None, None
    raw = candidates[-1]
    currency_match = re.search(r"€|\$|£|¥|₩|CHF|DKK|SEK|NOK|USD|EUR|GBP|CAD|AUD|SGD|HKD|AED", line or "", re.I)
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        value = None
    return raw, value, currency_match.group(0) if currency_match else None


def normalize_currency(raw, country=""):
    token = (raw or "").strip()
    if not token:
        return COUNTRY_CURRENCIES.get(country)
    upper = token.upper()
    if upper in {"A$", "AU$", "AUD$"}:
        return "AUD"
    if upper in {"CA$", "CAD$"}:
        return "CAD"
    if upper in {"HK$", "HKD$"}:
        return "HKD"
    if upper in {"S$", "SGD$"}:
        return "SGD"
    if upper in {"US$", "USD$"}:
        return "USD"
    return CURRENCY_ALIASES.get(token, token.upper())


def parse_price_number(raw):
    compact = re.sub(r"\s+", "", raw or "")
    compact = re.sub(r"(?<=\d)[oO](?=[,.])", "", compact)
    compact = re.sub(r"(?<=[,.])[oO]", "0", compact)
    compact = re.sub(r"(?<=\d)[oO](?=\d)", "0", compact)
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{2})?", compact):
        return float(compact.replace(",", ""))
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?", compact):
        return float(compact.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+[,.]\d{2}", compact):
        return float(compact.replace(",", "."))
    return float(re.sub(r"[,.]", "", compact))


def display_price(value):
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def strip_search_page_suffix(line, page_number=None):
    text = line or ""
    if page_number:
        text = re.sub(rf"[,;]\s*{re.escape(str(page_number))}\s*$", " ", text)
        text = re.sub(rf"\b(?:page|p\.?)\s*{re.escape(str(page_number))}\s*$", " ", text, flags=re.I)
    return text


def parse_price_v2(line, country="", page_number=None, require_edge=False):
    cleaned = strip_search_page_suffix(line, page_number)
    no_price = re.search(NO_PRICE_RE, cleaned, re.I) is not None
    text = re.sub(r"\b(19|20)\d{2}\b", " ", cleaned)
    text = re.sub(r"\b(?:page|p\.?)\s*\d{1,4}\b", " ", text, flags=re.I)
    text = re.sub(r"\b0\s*[,\.]\s*(?:187|375|5|50|70|75|750|150|1500)\s*(?:l|lt|liter|litre)?\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:37\.?5|75|187|375|500|750|1500)\s*(?:ml|cl)\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{1,3}\s*%\s*", " ", text)
    price_number = r"(?:\d{1,3}(?:[,\s.]\s*\d{3})+|\d{2,6}[oO]\s*[,\.]\s*[oO0]{2}|\d{2,6}(?:\s*[,\.]\s*[oO0]{2})?)"
    patterns = [
        rf"(?<![\w])(?:{PRICE_CURRENCY_RE})\s*{price_number}(?![\d%])",
        rf"(?<!\d){price_number}\s*(?:{PRICE_CURRENCY_RE})(?![\w])",
        r"(?<!\d)\d{1,3}(?:,\d{3})+(?:\.\d{2})?(?![\d%])",
        r"(?<!\d)\d{1,3}(?:,\s*\d{3})+(?:\.\d{2})?(?![\d%])",
        r"(?<!\d)\d{1,3}(?:[ .]\d{3})+(?:,\d{2})?(?![\d%])",
        r"(?<!\d)\d{2,6}[oO]\s*[,\.]\s*[oO0]{2}(?!\w)",
        r"(?<!\d)\d{2,6}\s*[,\.]\s*[oO0]{2}(?![\d%])",
        r"(?<!\d)\d{2,6}(?![\d%])",
    ]
    candidates = []
    used_spans = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if any(match.start() < end and match.end() > start for start, end in used_spans):
                continue
            raw = match.group(0).strip()
            raw_number = re.sub(PRICE_CURRENCY_RE, "", raw, flags=re.I)
            try:
                value = parse_price_number(raw_number)
            except ValueError:
                continue
            if value >= 10:
                tail = re.sub(r"[\s,.;:)\]]+$", "", text[match.end():])
                right_edge = not tail
                has_currency = re.search(PRICE_CURRENCY_RE, text[max(0, match.start() - 8):match.end() + 8], re.I) is not None
                candidates.append((match.start(), display_price(value), value, right_edge, has_currency))
                used_spans.append(match.span())
    currency_match = re.search(PRICE_CURRENCY_RE, cleaned, re.I)
    currency = normalize_currency(currency_match.group(0), country) if currency_match else normalize_currency("", country)
    if not candidates:
        return "", None, currency
    edge_candidates = [item for item in candidates if item[3]]
    if edge_candidates:
        _pos, raw, value, _edge, _currency = sorted(edge_candidates, key=lambda item: item[0])[-1]
        return raw, value, currency
    if require_edge:
        return "", None, currency
    if no_price:
        return "", None, currency
    currency_candidates = [item for item in candidates if item[4]]
    if currency_candidates:
        _pos, raw, value, _edge, _currency = sorted(currency_candidates, key=lambda item: item[0])[-1]
        return raw, value, currency
    _pos, raw, value, _edge, _currency = sorted(candidates, key=lambda item: item[0])[-1]
    return raw, value, currency


def extract_pdf_text(file_path):
    try:
        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def upsert_country(con, name):
    slug = slugify(name)
    con.execute(
        """
        insert into countries(slug, name, first_seen_at, last_seen_at)
        values(?, ?, ?, ?)
        on conflict(slug) do update set name=excluded.name, last_seen_at=excluded.last_seen_at
        """,
        (slug, name, now(), now()),
    )
    return con.execute("select id from countries where slug = ?", (slug,)).fetchone()[0]


def upsert_venue(con, result, country_id, country, city):
    item = result.get("item") or {}
    venue = ((item.get("pw") or {}).get("venue") or {})
    url = venue.get("URL") or ""
    slug = venue_slug_from_url(url)
    region_slug, lat, lng, star_map_url = location_from_result(result, country, city)
    con.execute(
        """
        insert into venues(slug, name, type, country_id, city, region_slug, lat, lng, address, google_maps_url, starwine_map_url, venue_url, first_seen_at, last_seen_at)
        values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(slug) do update set
          name=excluded.name,
          type=excluded.type,
          country_id=excluded.country_id,
          city=excluded.city,
          region_slug=excluded.region_slug,
          lat=excluded.lat,
          lng=excluded.lng,
          starwine_map_url=coalesce(excluded.starwine_map_url, venues.starwine_map_url),
          venue_url=excluded.venue_url,
          last_seen_at=excluded.last_seen_at
        """,
        (
            slug,
            venue.get("name") or slug,
            venue.get("type"),
            country_id,
            city,
            region_slug,
            lat,
            lng,
            venue.get("location"),
            None,
            star_map_url,
            url,
            now(),
            now(),
        ),
    )
    return con.execute("select id from venues where slug = ?", (slug,)).fetchone()[0]


def upsert_wine_list(con, result, venue_id):
    item = result.get("item") or {}
    wine_list = ((item.get("pw") or {}).get("wine_list") or {})
    starwine_list_id = str(wine_list.get("id") or "")
    if not starwine_list_id:
        return None
    download_url = wine_list.get("external") or wine_list.get("download_url") or wine_list.get("file") or ""
    con.execute(
        """
        insert into wine_lists(
          venue_id, starwine_list_id, label, download_url, file_url, file_view_url, updated_text, updated_date
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(starwine_list_id) do update set
          venue_id=excluded.venue_id,
          label=excluded.label,
          download_url=excluded.download_url,
          file_url=excluded.file_url,
          file_view_url=excluded.file_view_url,
          updated_text=excluded.updated_text,
          updated_date=excluded.updated_date
        """,
        (
            venue_id,
            starwine_list_id,
            f"Wine list {starwine_list_id}",
            download_url,
            wine_list.get("file"),
            wine_list.get("file_view"),
            wine_list.get("date"),
            wine_list.get("date"),
        ),
    )
    return con.execute("select * from wine_lists where starwine_list_id = ?", (starwine_list_id,)).fetchone()


def upsert_entry(con, result, venue_id, wine_list_id):
    item = result.get("item") or {}
    raw_text = item.get("text") or ""
    vintage = (re.search(r"\b(19|20)\d{2}\b", raw_text) or [None])[0]
    country = ((item.get("region") or {}).get("name") or None)
    price_text, price_value, currency = parse_price_v2(raw_text, country, result.get("page"))
    source_item_id = str(result.get("item_id") or "")
    if source_item_id:
        con.execute("delete from wine_entries where source_item_id = ?", (source_item_id,))
    con.execute(
        """
        insert into wine_entries(
          source_item_id, wine_list_id, venue_id, raw_text, vintage, region, country, price_text, price_value, currency, section, page_number
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_item_id or None,
            wine_list_id,
            venue_id,
            raw_text,
            vintage,
            country,
            country,
            price_text,
            price_value,
            currency,
            "Star Wine List search API",
            result.get("page"),
        ),
    )


def download_pdf(con, wine_list_row):
    file_url = wine_list_row["download_url"] or wine_list_row["file_url"]
    if not file_url:
        return False
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = DOWNLOAD_DIR / f"{wine_list_row['starwine_list_id']}.pdf"
    text_path = TEXT_DIR / f"{wine_list_row['starwine_list_id']}.txt"
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        return False
    body, content_type, _final_url = fetch_binary(file_url)
    if not body.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF response: {content_type}")
    pdf_path.write_bytes(body)
    text = extract_pdf_text(pdf_path)
    text_path.write_text(text, encoding="utf-8")
    con.execute(
        """
        update wine_lists set
          local_file_path=?,
          text_file_path=?,
          content_type=?,
          checksum=?,
          downloaded_at=?,
          indexed_at=?,
          last_error=null
        where id=?
        """,
        (
            str(pdf_path.relative_to(ROOT)),
            str(text_path.relative_to(ROOT)),
            content_type,
            hashlib.sha256(body).hexdigest(),
            now(),
            now(),
            wine_list_row["id"],
        ),
    )
    return True


def sync_page(con, page, query, region, download_pdfs, max_pdfs, pdf_counter):
    params = {"t": "wine-list", "page": page}
    if query:
        params["s"] = query
    if region:
        params["r"] = region
    url = f"{API_URL}?{urlencode(params)}"
    payload = fetch_json(url)
    count = 0
    downloaded = 0
    for result in payload.get("data") or []:
        if result.get("item_type") != "wine_list_line":
            continue
        country, city = country_city_from_result(result)
        country_id = upsert_country(con, country)
        venue_id = upsert_venue(con, result, country_id, country, city)
        wine_list_row = upsert_wine_list(con, result, venue_id)
        if not wine_list_row:
            continue
        upsert_entry(con, result, venue_id, wine_list_row["id"])
        count += 1
        if download_pdfs and pdf_counter[0] < max_pdfs:
            refreshed_row = con.execute("select * from wine_lists where id = ?", (wine_list_row["id"],)).fetchone()
            try:
                if download_pdf(con, refreshed_row):
                    downloaded += 1
                    pdf_counter[0] += 1
            except Exception as exc:
                con.execute("update wine_lists set last_error=? where id=?", (str(exc), wine_list_row["id"]))
    return payload, count, downloaded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="", help="Search term. Empty means all wine-list lines.")
    parser.add_argument("--region", default="", help="Star Wine List region slug, e.g. germany or hong-kong.")
    parser.add_argument("--pages", default="5", help="Number of pages, or 'all'.")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--delay-ms", type=int, default=800)
    parser.add_argument("--download-pdfs", action="store_true")
    parser.add_argument("--max-pdfs", type=int, default=50)
    parser.add_argument("--state-file", default="", help="Optional JSON state file for resumable long crawls.")
    args = parser.parse_args()

    init_db()
    delay = args.delay_ms / 1000
    total_entries = 0
    total_downloaded = 0
    pdf_counter = [0]
    with connect() as con:
        state_path = Path(args.state_file) if args.state_file else None
        if state_path and state_path.exists() and args.start_page == 1:
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                page = int(state.get("next_page") or args.start_page)
            except Exception:
                page = args.start_page
        else:
            page = args.start_page
        max_pages = None if args.pages == "all" else int(args.pages)
        seen_pages = 0
        while True:
            payload, entries, downloaded = sync_page(
                con,
                page,
                args.query,
                args.region,
                args.download_pdfs,
                args.max_pdfs,
                pdf_counter,
            )
            con.commit()
            if state_path:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(
                    json.dumps(
                        {
                            "next_page": page + 1,
                            "last_page": (payload.get("meta") or {}).get("last_page"),
                            "query": args.query,
                            "region": args.region,
                            "updated_at": now(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            total_entries += entries
            total_downloaded += downloaded
            meta = payload.get("meta") or {}
            print(f"page={page} entries={entries} pdfs={downloaded} total_entries={total_entries} api_total={meta.get('total')}")
            seen_pages += 1
            last_page = int(meta.get("last_page") or page)
            if page >= last_page:
                break
            if max_pages is not None and seen_pages >= max_pages:
                break
            page += 1
            time.sleep(delay)

    print(f"Done. entries={total_entries} pdfs={total_downloaded}")


if __name__ == "__main__":
    main()
