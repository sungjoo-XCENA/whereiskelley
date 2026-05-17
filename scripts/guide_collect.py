import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
import ssl
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "starwine.sqlite"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
DATA_DIR = ROOT / "data" / "guide"
PUBLIC_DATA_DIR = ROOT / "public" / "data"

GUIDE_SOURCES = {
    "laliste": {
        "name": "La Liste",
        "urls": [
            "https://www.laliste.com/lists/top-1000-restaurants",
            *[
                f"https://www.laliste.com/lists/top-1000-restaurants?2dbc56ae_page={page}"
                for page in range(2, 16)
            ],
        ],
    },
    "worlds50best": {
        "name": "World's 50 Best",
        "urls": [
            "https://www.theworlds50best.com/list/1-50",
            "https://www.theworlds50best.com/list/51-100",
            "https://www.theworlds50best.com/stories/News/the-worlds-50-best-restaurants-2025-1-50-list.html",
            "https://www.theworlds50best.com/stories/News/the-worlds-50-best-restaurants-2025-51-100-list.html",
        ],
    },
    "michelin": {
        "name": "MICHELIN Guide",
        "urls": [
            "https://guide.michelin.com/en/restaurants",
        ],
    },
}
SSL_CONTEXT = ssl._create_unverified_context()

WINE_LINK_RE = re.compile(
    r"\b(?:wine|wine-list|winelist|wines|cellar|beverage|drinks|drink|bar|menu|vin|vins|wein|vino|cave)\b",
    re.I,
)
WATCH_DEFAULTS = [
    {"keyword": "Romanee-Conti", "vintage": "", "active": True},
    {"keyword": "William Kelley", "vintage": "", "active": True},
]
CURRENCY_RE = r"HK\$|SG\$|S\$|A\$|C\$|US\$|\u20ac|\$|\u00a3|\u00a5|\u20a9|CHF|DKK|SEK|NOK|USD|EUR|GBP|CAD|AUD|SGD|HKD|AED|CNY|CZK|ARS|JPY|KRW"
CURRENCY_ALIASES = {
    "HK$": "HKD",
    "SG$": "SGD",
    "S$": "SGD",
    "A$": "AUD",
    "C$": "CAD",
    "US$": "USD",
    "\u20ac": "EUR",
    "$": "USD",
    "\u00a3": "GBP",
    "\u00a5": "JPY",
    "\u20a9": "KRW",
}


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = []
        self._current = None
        self._script_type = ""
        self._script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._current = {"href": attrs.get("href"), "text": ""}
        if tag == "script":
            self._script_type = attrs.get("type", "")
            self._script = []

    def handle_data(self, data):
        if self._current is not None:
            self._current["text"] += data
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._current is not None:
            self.links.append(self._current)
            self._current = None
        if tag == "script" and self._script is not None:
            self.scripts.append({"type": self._script_type, "text": "".join(self._script)})
            self._script = None
            self._script_type = ""


def now_sql():
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def write_progress(**payload):
    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = {
        "generatedAt": now_sql(),
        "status": "running",
        "phase": "",
        "message": "",
        "runId": None,
        "source": "",
        "currentTarget": "",
        "currentUrl": "",
        "targetsCollected": 0,
        "processedTargets": 0,
        "websitesChecked": 0,
        "totalWebsites": 0,
        "wineListsFound": 0,
        "wineLinesFound": 0,
        "errors": 0,
        "startedAt": "",
        "finishedAt": "",
        "elapsedSeconds": None,
        "estimatedRemainingSeconds": None,
        "estimatedFinishAt": "",
        "durationSeconds": None,
        "progressPercent": 0,
    }
    current.update(payload)
    (PUBLIC_DATA_DIR / "guide-progress.json").write_text(
        json.dumps(current, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    return con


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for code, source in GUIDE_SOURCES.items():
            con.execute(
                """
                insert into guide_sources(code, name, base_url, last_seen_at)
                values(?, ?, ?, current_timestamp)
                on conflict(code) do update set
                  name=excluded.name,
                  base_url=excluded.base_url,
                  last_seen_at=current_timestamp
                """,
                (code, source["name"], source["urls"][0]),
            )
        con.commit()


def fetch_text(url, timeout=30):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    }
    with urlopen(Request(url, headers=headers), timeout=timeout, context=SSL_CONTEXT) as response:
        content_type = response.headers.get("content-type", "")
        data = response.read()
    if "pdf" in content_type.lower() or urlparse(url).path.lower().endswith(".pdf"):
        return data, content_type
    return data.decode("utf-8", errors="replace"), content_type


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def target_key(name, city="", country=""):
    return "|".join([normalize_name(name), normalize_name(city), normalize_name(country)])


def clean_text(value):
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def jsonld_objects(parser):
    for script in parser.scripts:
        text = script["text"].strip()
        if not text:
            continue
        if script["type"] != "application/ld+json" and "__NEXT_DATA__" not in text[:200]:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        yield from walk_json(payload)


def extract_place_from_obj(obj):
    type_value = obj.get("@type") or obj.get("type") or obj.get("__typename") or ""
    type_text = " ".join(type_value) if isinstance(type_value, list) else str(type_value)
    name = obj.get("name") or obj.get("title") or obj.get("restaurantName")
    if not name or not re.search(r"restaurant|food|venue|place|card|item", type_text, re.I):
        return None
    address = obj.get("address") or {}
    if isinstance(address, dict):
        city = address.get("addressLocality") or address.get("city")
        country = address.get("addressCountry") or address.get("country")
        street = address.get("streetAddress")
    else:
        city = obj.get("city")
        country = obj.get("country")
        street = clean_text(address)
    geo = obj.get("geo") or {}
    url = obj.get("url") or obj.get("sameAs") or obj.get("website")
    if isinstance(url, list):
        url = url[0] if url else ""
    return {
        "name": clean_text(name),
        "city": clean_text(city or obj.get("city") or ""),
        "country": clean_text(country or obj.get("country") or ""),
        "address": clean_text(street or obj.get("address") or ""),
        "lat": geo.get("latitude") if isinstance(geo, dict) else None,
        "lng": geo.get("longitude") if isinstance(geo, dict) else None,
        "place_url": clean_text(url or obj.get("slug") or ""),
        "website_url": clean_text(obj.get("website") or obj.get("websiteUrl") or ""),
        "rank": obj.get("position") or obj.get("rank"),
        "score": obj.get("score"),
    }


def extract_places_from_html(html, source_url):
    parser = LinkParser()
    parser.feed(html)
    places = []
    for obj in jsonld_objects(parser):
        place = extract_place_from_obj(obj)
        if place and place["name"]:
            if place["place_url"] and place["place_url"].startswith("/"):
                place["place_url"] = urljoin(source_url, place["place_url"])
            places.append(place)
    places.extend(extract_laliste_cards(html, source_url))
    places.extend(extract_worlds50best_cards(html, source_url))
    seen = set()
    unique = []
    for place in places:
        if normalize_name(place["name"]) in {"restaurant", "restaurants", "hotel", "hotels"}:
            continue
        key = target_key(place["name"], place.get("city", ""), place.get("country", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(place)
    return unique, parser


def extract_laliste_cards(html, source_url):
    cards = []
    pattern = re.compile(
        r'<a[^>]+place_id="(?P<place_id>[^"]+)"[^>]+href="(?P<href>[^"]+)"[^>]*>.*?'
        r'fs-list-field="name"[^>]*>(?P<name>.*?)</div>.*?'
        r'fs-list-field="city"[^>]*>(?P<city>.*?)</div>.*?'
        r'fs-list-field="country"[^>]*>(?P<country>.*?)</div>.*?'
        r'fs-list-field="score"[^>]*>(?P<score>.*?)</div>',
        re.I | re.S,
    )
    for index, match in enumerate(pattern.finditer(html), start=1):
        cards.append({
            "name": clean_text(re.sub(r"<[^>]+>", " ", match.group("name"))),
            "city": clean_text(re.sub(r"<[^>]+>", " ", match.group("city"))),
            "country": clean_text(re.sub(r"<[^>]+>", " ", match.group("country"))),
            "address": "",
            "lat": None,
            "lng": None,
            "place_url": f"{source_url}#{match.group('place_id')}",
            "website_url": "",
            "rank": index,
            "score": clean_text(match.group("score")),
        })
    return cards


def extract_worlds50best_cards(html, source_url):
    cards = []
    pattern = re.compile(
        r'<div class="list-item"[^>]*>.*?'
        r'<p class="rank[^"]*"[^>]*>(?P<rank>\d+)</p>.*?'
        r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>\s*<h2>(?P<name>.*?)</h2>\s*</a>\s*<p>(?P<city>.*?)</p>',
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        cards.append({
            "name": clean_text(re.sub(r"<[^>]+>", " ", match.group("name"))),
            "city": clean_text(re.sub(r"<[^>]+>", " ", match.group("city"))),
            "country": "",
            "address": "",
            "lat": None,
            "lng": None,
            "place_url": urljoin(source_url, match.group("href")),
            "website_url": "",
            "rank": int(match.group("rank")),
            "score": None,
        })
    return cards


def source_id(con, code):
    row = con.execute("select id from guide_sources where code = ?", (code,)).fetchone()
    return row["id"]


def upsert_guide_place(con, source_code, source_url, place):
    sid = source_id(con, source_code)
    key = target_key(place["name"], place.get("city", ""), place.get("country", ""))
    cur = con.execute(
        """
        insert into guide_places(
          source_id, source_key, name, normalized_name, country, city, address, lat, lng,
          place_url, website_url, last_seen_at
        )
        values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        on conflict(source_id, source_key) do update set
          name=excluded.name,
          normalized_name=excluded.normalized_name,
          country=coalesce(nullif(excluded.country, ''), guide_places.country),
          city=coalesce(nullif(excluded.city, ''), guide_places.city),
          address=coalesce(nullif(excluded.address, ''), guide_places.address),
          lat=coalesce(excluded.lat, guide_places.lat),
          lng=coalesce(excluded.lng, guide_places.lng),
          place_url=coalesce(nullif(excluded.place_url, ''), guide_places.place_url),
          website_url=coalesce(nullif(excluded.website_url, ''), guide_places.website_url),
          last_seen_at=current_timestamp
        returning id
        """,
        (
            sid,
            key,
            place["name"],
            normalize_name(place["name"]),
            place.get("country", ""),
            place.get("city", ""),
            place.get("address", ""),
            place.get("lat"),
            place.get("lng"),
            place.get("place_url") or source_url,
            place.get("website_url", ""),
        ),
    )
    guide_place_id = cur.fetchone()["id"]
    con.execute(
        """
        insert into guide_rankings(guide_place_id, source_id, guide_year, list_name, rank, score, source_url)
        values(?, ?, ?, ?, ?, ?, ?)
        on conflict do nothing
        """,
        (guide_place_id, sid, None, GUIDE_SOURCES[source_code]["name"], place.get("rank"), place.get("score"), source_url),
    )
    return guide_place_id


def upsert_target(con, place, source_code):
    if normalize_name(place["name"]) in {"restaurant", "restaurants", "hotel", "hotels"}:
        return
    key = target_key(place["name"], place.get("city", ""), place.get("country", ""))
    row = con.execute("select * from restaurant_targets where normalized_key = ?", (key,)).fetchone()
    sources = []
    if row:
        try:
            sources = json.loads(row["sources_json"] or "[]")
        except json.JSONDecodeError:
            sources = []
    if source_code not in sources:
        sources.append(source_code)
    priority = max(1, len(sources))
    con.execute(
        """
        insert into restaurant_targets(
          normalized_key, name, normalized_name, country, city, address, lat, lng,
          website_url, sources_json, source_count, priority, last_seen_at
        )
        values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        on conflict(normalized_key) do update set
          website_url=case
            when excluded.website_url != '' then excluded.website_url
            when restaurant_targets.website_url like '%laliste.com%' then ''
            else restaurant_targets.website_url
          end,
          status=case
            when excluded.website_url = '' and restaurant_targets.website_url like '%laliste.com%' then 'not_checked'
            else restaurant_targets.status
          end,
          sources_json=excluded.sources_json,
          source_count=excluded.source_count,
          priority=excluded.priority,
          last_seen_at=current_timestamp
        """,
        (
            key,
            place["name"],
            normalize_name(place["name"]),
            place.get("country", ""),
            place.get("city", ""),
            place.get("address", ""),
            place.get("lat"),
            place.get("lng"),
            place.get("website_url", ""),
            json.dumps(sources),
            len(sources),
            priority,
        ),
    )


def discover_website_from_place_page(place_url):
    if not place_url:
        return ""
    try:
        html, content_type = fetch_text(place_url, timeout=20)
    except Exception:
        return ""
    if not isinstance(html, str) or "html" not in content_type.lower():
        return ""
    parser = LinkParser()
    parser.feed(html)
    for link in parser.links:
        text = clean_text(link.get("text", ""))
        href = urljoin(place_url, link.get("href", ""))
        host = urlparse(href).netloc.lower()
        if not host or any(blocked in host for blocked in ["michelin", "laliste", "theworlds50best", "facebook", "instagram"]):
            continue
        if re.search(r"\b(?:website|official|site|restaurant)\b", text, re.I):
            return href
    return ""


def candidate_wine_links(base_url, html):
    parser = LinkParser()
    parser.feed(html)
    links = []
    for link in parser.links:
        href = urljoin(base_url, link.get("href", ""))
        text = clean_text(link.get("text", ""))
        path = urlparse(href).path.lower()
        if WINE_LINK_RE.search(text) or WINE_LINK_RE.search(path) or path.endswith(".pdf"):
            links.append({"url": href, "text": text})
    seen = set()
    unique = []
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        unique.append(link)
    return unique[:20]


def parse_price(line):
    if re.search(r"\b(?:on request|market price|ask|sold out|n/a)\b", line, re.I):
        return "", None, ""
    currency_match = re.search(CURRENCY_RE, line, re.I)
    currency = ""
    if currency_match:
        token = currency_match.group(0)
        currency = CURRENCY_ALIASES.get(token, token.upper())
    numbers = list(re.finditer(r"(?<!\d)(?:\d{1,3}(?:[,\s.]\d{3})+|\d{2,6})(?:[,.]\d{2})?(?!\d)", line))
    if not numbers:
        return "", None, currency
    raw = numbers[-1].group(0)
    compact = re.sub(r"\s+", "", raw)
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{2})?", compact):
        value = float(compact.replace(",", ""))
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?", compact):
        value = float(compact.replace(".", "").replace(",", "."))
    elif re.fullmatch(r"\d+[,.]\d{2}", compact):
        value = float(compact.replace(",", "."))
    else:
        value = float(re.sub(r"[,.]", "", compact))
    if value < 10:
        return "", None, currency
    return raw, value, currency


def likely_wine_line(line, watches):
    text = clean_text(line)
    if len(text) < 8 or len(text) > 260:
        return False
    if any(normalize_name(watch["keyword"]) in normalize_name(text) for watch in watches if watch.get("active", True)):
        return True
    if re.search(r"\b(19|20)\d{2}\b", text) and parse_price(text)[1]:
        return True
    return False


def html_to_lines(html):
    text = re.sub(r"(?i)<\s*(br|p|div|li|tr|td|th|h[1-6])\b[^>]*>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = []
    for line in text.splitlines():
        cleaned = clean_text(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def save_wine_source(con, target, url, source_type, content, text, error=""):
    target_id = target["id"]
    digest = hashlib.sha256(content if isinstance(content, bytes) else content.encode("utf-8", errors="ignore")).hexdigest()
    stem = f"{target_id}-{digest[:12]}"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    content_path = DATA_DIR / f"{stem}.{'pdf' if source_type == 'pdf' else 'html'}"
    text_path = DATA_DIR / f"{stem}.txt"
    mode = "wb" if isinstance(content, bytes) else "w"
    if mode == "wb":
        content_path.write_bytes(content)
    else:
        content_path.write_text(content, encoding="utf-8")
    text_path.write_text(text or "", encoding="utf-8")
    cur = con.execute(
        """
        insert into wine_list_sources(
          target_id, url, source_type, status, content_path, text_path, checksum,
          last_checked_at, parser_status, last_error
        )
        values(?, ?, ?, ?, ?, ?, ?, current_timestamp, ?, ?)
        on conflict(target_id, url) do update set
          source_type=excluded.source_type,
          status=excluded.status,
          content_path=excluded.content_path,
          text_path=excluded.text_path,
          checksum=excluded.checksum,
          last_checked_at=current_timestamp,
          parser_status=excluded.parser_status,
          last_error=excluded.last_error
        returning id
        """,
        (
            target_id,
            url,
            source_type,
            "found" if not error else "review",
            str(content_path.relative_to(ROOT)),
            str(text_path.relative_to(ROOT)),
            digest,
            "parsed" if text else "review",
            error,
        ),
    )
    return cur.fetchone()["id"]


def pdf_text(pdf_path):
    script = ROOT / "scripts" / "extract_pdf_text.py"
    result = subprocess.run([sys.executable, str(script), str(pdf_path)], capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    return payload.get("text") if payload.get("ok") else ""


def load_watchlist():
    path = PUBLIC_DATA_DIR / "watchlist.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            watches = payload.get("watches") if isinstance(payload, dict) else payload
            return [watch for watch in watches if watch.get("keyword")]
        except Exception:
            pass
    return WATCH_DEFAULTS


def scan_wine_source(con, target, url, watches):
    try:
        content, content_type = fetch_text(url, timeout=30)
        source_type = "pdf" if "pdf" in content_type.lower() or urlparse(url).path.lower().endswith(".pdf") else "html"
        if source_type == "pdf":
            temp = DATA_DIR / "_temp.pdf"
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(content)
            text = pdf_text(temp)
        else:
            text = html_to_lines(content)
        source_id = save_wine_source(con, target, url, source_type, content, text)
        lines = [clean_text(line) for line in re.split(r"[\r\n]+", text or "") if likely_wine_line(line, watches)]
        inserted = 0
        for line in lines[:1000]:
            vintage_match = re.search(r"\b(19|20)\d{2}\b", line)
            price_text, price_value, currency = parse_price(line)
            con.execute(
                """
                insert into guide_wine_entries(
                  target_id, wine_list_source_id, raw_text, vintage, price_text,
                  price_value, currency, source_url, source_type, last_seen_at
                )
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(target_id, source_url, raw_text) do update set
                  vintage=excluded.vintage,
                  price_text=excluded.price_text,
                  price_value=excluded.price_value,
                  currency=excluded.currency,
                  last_seen_at=current_timestamp
                """,
                (
                    target["id"],
                    source_id,
                    line,
                    vintage_match.group(0) if vintage_match else "",
                    price_text,
                    price_value,
                    currency,
                    url,
                    source_type,
                ),
            )
            inserted += 1
        con.execute("update wine_list_sources set line_count=? where id=?", (inserted, source_id))
        return 1, inserted, ""
    except Exception as exc:
        con.execute(
            "update restaurant_targets set status='review', last_error=?, last_checked_at=current_timestamp where id=?",
            (str(exc), target["id"]),
        )
        return 0, 0, str(exc)


def collect_sources(con, sources, max_source_items, run_id, resolve_websites=False):
    collected = 0
    for code in sources:
        source = GUIDE_SOURCES[code]
        for url in source["urls"]:
            write_progress(
                runId=run_id,
                phase="reading_guides",
                source=code,
                currentUrl=url,
                targetsCollected=collected,
                message=f"Reading {source['name']} candidates.",
            )
            try:
                html, content_type = fetch_text(url)
            except Exception as exc:
                write_progress(
                    runId=run_id,
                    phase="reading_guides",
                    source=code,
                    currentUrl=url,
                    targetsCollected=collected,
                    errors=1,
                    message=f"Could not read {source['name']}: {exc}",
                )
                continue
            if not isinstance(html, str):
                continue
            places, _parser = extract_places_from_html(html, url)
            for place in places[:max_source_items or None]:
                write_progress(
                    runId=run_id,
                    phase="saving_targets",
                    source=code,
                    currentTarget=place.get("name", ""),
                    currentUrl=place.get("place_url", "") or url,
                    targetsCollected=collected,
                    message="Saving guide place candidates.",
                )
                if resolve_websites and not place.get("website_url"):
                    place["website_url"] = discover_website_from_place_page(place.get("place_url", ""))
                upsert_guide_place(con, code, url, place)
                upsert_target(con, place, code)
                collected += 1
                if collected % 10 == 0:
                    con.commit()
    return collected


def discover_targets(con, max_targets, run_id, target_count):
    watches = load_watchlist()
    query = """
        select * from restaurant_targets
        where website_url is not null and website_url != ''
        order by priority desc, last_checked_at is not null, name
    """
    params = ()
    if max_targets and max_targets > 0:
        query += " limit ?"
        params = (max_targets,)
    rows = con.execute(query, params).fetchall()
    websites = 0
    sources_found = 0
    lines_found = 0
    errors = 0
    total_websites = len(rows)
    write_progress(
        runId=run_id,
        phase="checking_websites",
        targetsCollected=target_count,
        totalWebsites=total_websites,
        message=f"Checking {total_websites} official websites for wine lists.",
    )
    for row in rows:
        target = dict(row)
        websites += 1
        write_progress(
            runId=run_id,
            phase="checking_websites",
            currentTarget=target.get("name", ""),
            currentUrl=target.get("website_url", ""),
            targetsCollected=target_count,
            websitesChecked=websites,
            totalWebsites=total_websites,
            wineListsFound=sources_found,
            wineLinesFound=lines_found,
            errors=errors,
            message="Opening official website and looking for wine-related links.",
        )
        try:
            html, content_type = fetch_text(target["website_url"], timeout=25)
            if not isinstance(html, str):
                continue
            links = candidate_wine_links(target["website_url"], html)
            if not links:
                con.execute(
                    "update restaurant_targets set status='no_wine_list', last_checked_at=current_timestamp where id=?",
                    (target["id"],),
                )
                continue
            target_sources = 0
            target_lines = 0
            for link in links[:5]:
                write_progress(
                    runId=run_id,
                    phase="scanning_wine_lists",
                    currentTarget=target.get("name", ""),
                    currentUrl=link["url"],
                    targetsCollected=target_count,
                    websitesChecked=websites,
                    totalWebsites=total_websites,
                    wineListsFound=sources_found,
                    wineLinesFound=lines_found,
                    errors=errors,
                    message="Reading a candidate wine list.",
                )
                found, lines, error = scan_wine_source(con, target, link["url"], watches)
                target_sources += found
                target_lines += lines
                if error:
                    errors += 1
            status = "found" if target_sources else "review"
            con.execute(
                "update restaurant_targets set status=?, last_checked_at=current_timestamp, last_error=null where id=?",
                (status, target["id"]),
            )
            sources_found += target_sources
            lines_found += target_lines
            write_progress(
                runId=run_id,
                phase="checking_websites",
                currentTarget=target.get("name", ""),
                currentUrl=target.get("website_url", ""),
                targetsCollected=target_count,
                websitesChecked=websites,
                totalWebsites=total_websites,
                wineListsFound=sources_found,
                wineLinesFound=lines_found,
                errors=errors,
                message="Finished this website.",
            )
        except Exception as exc:
            errors += 1
            con.execute(
                "update restaurant_targets set status='error', last_error=?, last_checked_at=current_timestamp where id=?",
                (str(exc), target["id"]),
            )
            write_progress(
                runId=run_id,
                phase="checking_websites",
                currentTarget=target.get("name", ""),
                currentUrl=target.get("website_url", ""),
                targetsCollected=target_count,
                websitesChecked=websites,
                totalWebsites=total_websites,
                wineListsFound=sources_found,
                wineLinesFound=lines_found,
                errors=errors,
                message=f"Website check failed: {exc}",
            )
    return websites, sources_found, lines_found, errors


def export_status(con, run_id):
    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    counts = {
        "targets": con.execute("select count(*) from restaurant_targets").fetchone()[0],
        "sources": con.execute("select count(*) from wine_list_sources").fetchone()[0],
        "wineLines": con.execute("select count(*) from guide_wine_entries").fetchone()[0],
        "review": con.execute("select count(*) from restaurant_targets where status in ('review','error')").fetchone()[0],
        "found": con.execute("select count(*) from restaurant_targets where status = 'found'").fetchone()[0],
    }
    source_counts = [
        dict(row)
        for row in con.execute(
            """
            select s.code, s.name, count(p.id) as places
            from guide_sources s
            left join guide_places p on p.source_id = s.id
            group by s.id, s.code, s.name
            order by s.code
            """
        )
    ]
    run = con.execute("select * from guide_collection_runs where id=?", (run_id,)).fetchone()
    targets = [
        dict(row)
        for row in con.execute(
            """
            select name, city, country, website_url, sources_json, source_count, priority, status, last_checked_at, last_error
            from restaurant_targets
            order by priority desc, name
            limit 120
            """
        )
    ]
    hits = [
        dict(row)
        for row in con.execute(
            """
            select e.raw_text, e.vintage, e.price_text, e.price_value, e.currency, t.name, t.city, t.country, e.source_url
            from guide_wine_entries e
            join restaurant_targets t on t.id = e.target_id
            order by e.last_seen_at desc
            limit 300
            """
        )
    ]
    (PUBLIC_DATA_DIR / "guide-status.json").write_text(
        json.dumps(
            {"generatedAt": now_sql(), "counts": counts, "sourceCounts": source_counts, "lastRun": dict(run) if run else None},
            ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )
    (PUBLIC_DATA_DIR / "guide-targets.json").write_text(json.dumps(targets, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (PUBLIC_DATA_DIR / "guide-watch-hits.json").write_text(json.dumps(hits, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="michelin,laliste,worlds50best")
    parser.add_argument("--max-source-items", type=int, default=0, help="Per source URL. 0 means all.")
    parser.add_argument("--max-targets", type=int, default=0, help="Official websites to check. 0 means all.")
    parser.add_argument("--discover", action="store_true", help="Check target websites for wine lists.")
    parser.add_argument("--no-discover", action="store_true")
    parser.add_argument("--resolve-websites", action="store_true", help="Try to resolve official websites while reading guide sources.")
    args = parser.parse_args()

    init_db()
    sources = [item.strip() for item in args.sources.split(",") if item.strip() in GUIDE_SOURCES]
    with connect() as con:
        cur = con.execute(
            "insert into guide_collection_runs(started_at, status, sources_requested) values(?, 'running', ?)",
            (now_sql(), ",".join(sources)),
        )
        run_id = cur.lastrowid
        errors = 0
        write_progress(
            runId=run_id,
            status="running",
            phase="starting",
            source=",".join(sources),
            message="Starting guide collection.",
        )
        try:
            target_count = collect_sources(con, sources, args.max_source_items, run_id, args.resolve_websites)
            websites_checked = wine_lists_found = wine_lines_found = 0
            if args.discover and not args.no_discover:
                websites_checked, wine_lists_found, wine_lines_found, errors = discover_targets(con, args.max_targets, run_id, target_count)
            con.execute(
                """
                update guide_collection_runs
                set finished_at=?, status='completed', target_count=?, websites_checked=?,
                    wine_lists_found=?, wine_lines_found=?, errors=?
                where id=?
                """,
                (now_sql(), target_count, websites_checked, wine_lists_found, wine_lines_found, errors, run_id),
            )
            write_progress(
                runId=run_id,
                status="completed",
                phase="completed",
                targetsCollected=target_count,
                websitesChecked=websites_checked,
                totalWebsites=websites_checked,
                wineListsFound=wine_lists_found,
                wineLinesFound=wine_lines_found,
                errors=errors,
                message="Guide collection completed.",
            )
        except Exception as exc:
            con.execute(
                "update guide_collection_runs set finished_at=?, status='error', errors=errors+1, notes=? where id=?",
                (now_sql(), str(exc), run_id),
            )
            write_progress(
                runId=run_id,
                status="error",
                phase="error",
                errors=errors + 1,
                message=str(exc),
            )
            raise
        finally:
            export_status(con, run_id)
        con.commit()
        print(f"targets={target_count} websites={websites_checked} wine_lists={wine_lists_found} wine_lines={wine_lines_found} errors={errors}")


if __name__ == "__main__":
    main()
