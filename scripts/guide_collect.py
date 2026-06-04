import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import ssl
import unicodedata
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "db" / "schema.sql"
DATA_DIR = ROOT / "data" / "guide"
PUBLIC_DATA_DIR = ROOT / "public" / "data"


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

WINE_LINK_STRONG_RE = re.compile(
    r"\b(?:wine|wine-list|winelist|winecard|wine-menu|wines|cellar|sommelier|champagne|"
    r"beverage|beverages|drinks|drink|drink-list|drink-menu|bar-menu|"
    r"vin|vins|carte-des-vins|carte\s+des\s+vins|carte\s+vins|cave|boisson|boissons|"
    r"wein|weine|weinkarte|getranke|getraenke|"
    r"vino|vini|carta-dei-vini|carta\s+dei\s+vini|"
    r"lista-de-vinos|lista\s+de\s+vinos|carta\s+de\s+vinos|bebida|bebidas|bodega|"
    r"vinho|vinhos|carta\s+de\s+vinhos|"
    r"wijn|wijnen|wijnkaart|dranken|"
    r"vinkort|vinliste|dryck|drycker|dryckeslista|"
    r"viini|viinit|viinilista|sake)\b",
    re.I,
)
WINE_LINK_WEAK_RE = re.compile(r"\b(?:menu|bar|pairing|tasting|omakase|degustation|degustazione|degustacion)\b", re.I)
NON_WINE_MENU_RE = re.compile(r"\b(?:food|lunch|dinner|breakfast|brunch|tasting-menu|a-la-carte|dessert)\b", re.I)
CRAWL_SKIP_RE = re.compile(
    r"\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|zip|mp4|mov|avi|woff2?|ttf|eot)(?:[?#]|$)|"
    r"\b(?:privacy|terms|cookie|career|jobs|press|newsletter|gift-card|giftcard|voucher|"
    r"instagram|facebook|twitter|linkedin|youtube|tripadvisor|reservation|booking|book-a-table|"
    r"room|rooms|suite|suites|hotel|accommodation|zimmer|chambre|camera|habitacion|spa|wellness)\b",
    re.I,
)
WINE_TEXT_RE = re.compile(
    r"\b(?:"
    r"burgundy|bourgogne|bordeaux|champagne|"
    r"chablis|cote\s+d['’]?or|côte\s+d['’]?or|cote\s+de\s+nuits|côte\s+de\s+nuits|cote\s+de\s+beaune|côte\s+de\s+beaune|"
    r"meursault|puligny|chassagne|volnay|pommard|gevrey|chambolle|vosne|nuits|beaune|morey|vougeot|"
    r"margaux|pauillac|pomerol|saint[-\s]?emilion|st[-\s]?emilion|saint[-\s]?julien|st[-\s]?julien|saint[-\s]?estephe|st[-\s]?estephe|"
    r"pessac|leognan|léognan|sauternes|barsac|medoc|médoc|haut[-\s]?medoc|haut[-\s]?médoc|"
    r"reims|epernay|épernay|montagne\s+de\s+reims|cote\s+des\s+blancs|côte\s+des\s+blancs|vallee\s+de\s+la\s+marne|vallée\s+de\s+la\s+marne|"
    r"brut|extra\s+brut|blanc\s+de\s+blancs|blanc\s+de\s+noirs|"
    r"brut|extra\s+brut|sec|demi-sec|cru|village|villages|domaine|domain|chateau|château|weingut|estate|reserve|reserva|grand|premier|"
    r"pinot\s+noir|chardonnay|cabernet\s+sauvignon|merlot"
    r")\b",
    re.I,
)
CORE_WINE_TEXT_RE = re.compile(
    r"\b(?:burgundy|bourgogne|bordeaux|champagne|chablis|meursault|puligny|chassagne|volnay|pommard|gevrey|chambolle|vosne|"
    r"margaux|pauillac|pomerol|saint[-\s]?emilion|st[-\s]?emilion|sauternes|medoc|médoc|reims|epernay|épernay|"
    r"cote\s+d['’]?or|côte\s+d['’]?or|cote\s+de\s+nuits|côte\s+de\s+nuits|cote\s+des\s+blancs|côte\s+des\s+blancs)\b",
    re.I,
)
BAD_LINE_RE = re.compile(
    r"https?://|url\(|background:|copyright|all rights reserved|michelin guide|screenshot|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b|"
    r"\b(?:wait_for|function|script|cookie|analytics|instagram|facebook|google|schema|"
    r"privacy|terms|newsletter|reservation|booking|award|posted|edition)\b",
    re.I,
)
WINE_TEXT_RE = re.compile(
    r"\b(?:burgundy|bourgogne|bordeaux|champagne|chablis|cote\s+d['’]?or|cote\s+de\s+nuits|cote\s+de\s+beaune|"
    r"meursault|puligny|chassagne|volnay|pommard|gevrey|chambolle|vosne|nuits|beaune|morey|vougeot|"
    r"margaux|pauillac|pomerol|saint[-\s]?emilion|st[-\s]?emilion|saint[-\s]?julien|st[-\s]?julien|"
    r"saint[-\s]?estephe|st[-\s]?estephe|pessac|leognan|sauternes|barsac|medoc|haut[-\s]?medoc|"
    r"reims|epernay|montagne\s+de\s+reims|cote\s+des\s+blancs|vallee\s+de\s+la\s+marne|brut|extra\s+brut|"
    r"blanc\s+de\s+blancs|blanc\s+de\s+noirs|sec|demi-sec|cru|village|villages|domaine|domain|chateau|"
    r"weingut|estate|reserve|reserva|grand|premier|pinot\s+noir|chardonnay|cabernet\s+sauvignon|merlot)\b",
    re.I,
)
CORE_WINE_TEXT_RE = re.compile(
    r"\b(?:burgundy|bourgogne|bordeaux|champagne|chablis|meursault|puligny|chassagne|volnay|pommard|gevrey|"
    r"chambolle|vosne|margaux|pauillac|pomerol|saint[-\s]?emilion|st[-\s]?emilion|sauternes|medoc|"
    r"reims|epernay|cote\s+d['’]?or|cote\s+de\s+nuits|cote\s+des\s+blancs)\b",
    re.I,
)
PRICE_NUMBER_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:[,\s.]\d{3})+|\d{2,6})(?:[,.]\d{2})?(?!\d)")
WATCH_DEFAULTS = [
    {"keyword": "Romanee-Conti", "vintage": "", "active": True},
    {"keyword": "William Kelley", "vintage": "", "active": True},
]
CURRENCY_RE = r"HK\$|SG\$|S\$|A\$|C\$|US\$|\u20ac|\$|\u00a3|\u00a5|\u20a9|(?<![A-Z])(?:CHF|DKK|SEK|NOK|USD|EUR|GBP|CAD|AUD|SGD|HKD|AED|CNY|CZK|ARS|JPY|KRW)(?![A-Z])"
MAX_DISCOVERY_FETCHES = int(os.environ.get("WHEREISKELLEY_MAX_DISCOVERY_FETCHES", "18"))
MAX_DISCOVERY_DEPTH = int(os.environ.get("WHEREISKELLEY_MAX_DISCOVERY_DEPTH", "2"))
MAX_WEAK_DISCOVERY_FETCHES = int(os.environ.get("WHEREISKELLEY_MAX_WEAK_DISCOVERY_FETCHES", "4"))
STRONG_LINK_SCORE = 70
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


def fold_text(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


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
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    return con


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = connect()
    try:
        has_guide_sources = con.execute(
            "select 1 from sqlite_master where type = 'table' and name = 'guide_sources'"
        ).fetchone()
        if not has_guide_sources:
            con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            con.commit()
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
    finally:
        con.close()


def fetch_text(url, timeout=8):
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


def find_node():
    bundled = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe"
    )
    return str(bundled) if bundled.exists() else "node"


def render_page_text(url):
    script = ROOT / "scripts" / "render_page_text.mjs"
    if not script.exists():
        return ""
    try:
        result = subprocess.run(
            [find_node(), str(script), url],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=12,
        )
    except Exception:
        return ""
    if result.returncode != 0 and not result.stdout:
        return ""
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    return payload.get("text") if payload.get("ok") else ""


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


def registrable_root(host):
    host = (host or "").lower().strip(".")
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3 and parts[-2] in {"ac", "co", "com", "edu", "gov", "net", "org"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def same_site_or_wine_host(base_url, href):
    base_host = urlparse(base_url).netloc.lower()
    host = urlparse(href).netloc.lower()
    if not base_host or not host:
        return False
    base_root = registrable_root(base_host)
    host_root = registrable_root(host)
    return host == base_host or host_root == base_root or host.startswith("wine.") or ".wine." in host


WINE_SOURCE_URL_RE = re.compile(
    r"(?:"
    r"wine[-_/ ]?list|winelist|wine[-_/ ]?card|wine[-_/ ]?menu|"
    r"wine[-_/ ]?book|wine[-_/ ]?cellar|"
    r"wijnkaart|weinkarte|wein[-_/ ]?karte|"
    r"carte[-_/ ]?des[-_/ ]?vins|carte[-_/ ]?vins|"
    r"carta[-_/ ]?dei[-_/ ]?vini|lista[-_/ ]?de[-_/ ]?vinos|carta[-_/ ]?de[-_/ ]?vinos|"
    r"carta[-_/ ]?de[-_/ ]?vinhos|vinkort|vinliste|dryckeslista|viinilista|"
    r"drink[-_/ ]?list|drink[-_/ ]?menu|drinks[-_/ ]?menu|beverage[-_/ ]?list|beverage[-_/ ]?menu"
    r")",
    re.I,
)
GENERIC_SOURCE_PATH_RE = re.compile(
    r"^/?$|^/(?:restaurant|restaurants|menu|menus|food|dining|about|contact|home|en|fr|de|it|es|nl|ja|ko)/?$",
    re.I,
)


def source_url_signal(url, source_type, link_score=0):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = fold_text(unescape(parsed.path or "").replace("_", "-"))
    if source_type == "pdf" or path.endswith(".pdf"):
        return True
    if host.startswith("wine.") or ".wine." in host:
        return True
    if WINE_SOURCE_URL_RE.search(path):
        return True
    if int(link_score or 0) >= 70 and not GENERIC_SOURCE_PATH_RE.search(path):
        return True
    return False


def generated_wine_link_candidates(base_url):
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []
    base_host = parsed.netloc.lower()
    root = registrable_root(base_host)
    candidates = [
        (f"{parsed.scheme}://wine.{root}/", "Wine subdomain", 150),
    ]
    for path in ["/wine/", "/wine-list/", "/winelist/", "/drinks/", "/drink-list/", "/beverage/", "/vin/", "/vins/", "/carte-des-vins/"]:
        candidates.append((urljoin(f"{parsed.scheme}://{base_host}", path), path.strip("/"), 80))
    return [{"url": url, "text": text, "score": score} for url, text, score in candidates]


def candidate_wine_links(base_url, html, include_review_candidates=True):
    parser = LinkParser()
    parser.feed(html)
    links = generated_wine_link_candidates(base_url)
    for link in parser.links:
        href = urljoin(base_url, link.get("href", ""))
        text = clean_text(link.get("text", ""))
        parsed = urlparse(href)
        host = parsed.netloc.lower()
        path = urlparse(href).path.lower()
        haystack = fold_text(" ".join([text, host, path]).replace("_", "-"))
        score = 0
        if path.endswith(".pdf"):
            score += 20
        if host.startswith("wine.") or ".wine." in host:
            score += 120
        if WINE_LINK_STRONG_RE.search(haystack):
            score += 80
        if WINE_LINK_WEAK_RE.search(haystack):
            score += 10
        if NON_WINE_MENU_RE.search(haystack) and not WINE_LINK_STRONG_RE.search(haystack):
            score -= 60
        if include_review_candidates and same_site_or_wine_host(base_url, href) and score <= 0:
            if not NON_WINE_MENU_RE.search(haystack) and not re.search(r"\b(?:privacy|terms|contact|gallery|news|blog|reservation|book|career|gift)\b", haystack, re.I):
                score = 1
        if score > 0:
            links.append({"url": href, "text": text, "score": score})
    scored = sorted(links, key=lambda item: item.get("score", 0), reverse=True)
    strong_links = [link for link in scored if link.get("score", 0) >= 70]
    review_links = [link for link in scored if link.get("score", 0) < 70]
    candidates = [*strong_links, *review_links]
    seen = set()
    unique = []
    for link in candidates:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        unique.append(link)
    return unique[:60]


def normalize_crawl_url(base_url, href):
    if not href or href.startswith(("mailto:", "tel:", "sms:", "javascript:")):
        return ""
    url = urljoin(base_url, href).split("#", 1)[0]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if not same_site_or_wine_host(base_url, url):
        return ""
    haystack = fold_text(" ".join([parsed.netloc.lower(), parsed.path.lower()]))
    if CRAWL_SKIP_RE.search(haystack) and not WINE_LINK_STRONG_RE.search(haystack):
        return ""
    return url


def crawlable_page_links(base_url, page_url, html):
    parser = LinkParser()
    parser.feed(html)
    links = []
    for link in parser.links:
        url = normalize_crawl_url(base_url, urljoin(page_url, link.get("href", "")))
        if not url:
            continue
        text = clean_text(link.get("text", ""))
        parsed = urlparse(url)
        haystack = fold_text(" ".join([text, parsed.netloc.lower(), parsed.path.lower()]).replace("_", "-"))
        score = 1
        if parsed.path.lower().endswith(".pdf"):
            score += 30
        if parsed.netloc.lower().startswith("wine.") or ".wine." in parsed.netloc.lower():
            score += 120
        if WINE_LINK_STRONG_RE.search(haystack):
            score += 80
        if WINE_LINK_WEAK_RE.search(haystack):
            score += 10
        links.append({"url": url, "text": text, "score": score})
    return links


def discover_candidate_wine_links(base_url, html, max_pages=40, max_depth=None, max_weak_pages=None):
    max_fetches = min(max_pages or MAX_DISCOVERY_FETCHES, MAX_DISCOVERY_FETCHES)
    max_depth = MAX_DISCOVERY_DEPTH if max_depth is None else max_depth
    max_weak_pages = MAX_WEAK_DISCOVERY_FETCHES if max_weak_pages is None else max_weak_pages
    links = candidate_wine_links(base_url, html)
    queue = sorted(crawlable_page_links(base_url, base_url, html), key=lambda item: item.get("score", 0), reverse=True)
    for item in queue:
        item["depth"] = 1
    seen = {link["url"].split("#", 1)[0] for link in links}
    queued = {link["url"].split("#", 1)[0] for link in queue}
    scanned_pages = 0
    weak_scanned_pages = 0
    while queue and scanned_pages < max_fetches:
        queue.sort(key=lambda item: item.get("score", 0), reverse=True)
        link = queue.pop(0)
        key = link["url"].split("#", 1)[0]
        if key in seen:
            continue
        score = int(link.get("score", 0) or 0)
        depth = int(link.get("depth", 1) or 1)
        if score < STRONG_LINK_SCORE:
            if weak_scanned_pages >= max_weak_pages:
                continue
            weak_scanned_pages += 1
        seen.add(key)
        links.append(link)
        if urlparse(link["url"]).path.lower().endswith(".pdf"):
            continue
        if depth >= max_depth:
            continue
        try:
            content, content_type = fetch_text(link["url"], timeout=5)
        except Exception:
            continue
        if not isinstance(content, str) or "html" not in content_type.lower():
            continue
        scanned_pages += 1
        folded_content = fold_text(content[:12000])
        if CORE_WINE_TEXT_RE.search(folded_content) and score >= 10:
            link["score"] = score + 35
        child_links = crawlable_page_links(base_url, link["url"], content)
        for child in child_links:
            key = child["url"].split("#", 1)[0]
            if key in seen or key in queued:
                continue
            child["depth"] = depth + 1
            queued.add(key)
            queue.append(child)
    return sorted(links, key=lambda item: item.get("score", 0), reverse=True)


def parse_price(line):
    if re.search(r"\b(?:on request|market price|ask|sold out|n/a)\b", line, re.I):
        return "", None, ""
    currency_match = re.search(CURRENCY_RE, line, re.I)
    currency = ""
    if currency_match:
        token = currency_match.group(0)
        currency = CURRENCY_ALIASES.get(token, token.upper())
    numbers = list(PRICE_NUMBER_RE.finditer(line))
    if not numbers:
        return "", None, currency
    for match in reversed(numbers):
        raw = match.group(0)
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
            continue
        if not currency and re.fullmatch(r"(?:19|20)\d{2}", compact):
            continue
        return raw, value, currency
    return "", None, currency


def candidate_text_lines(text):
    raw_lines = [clean_text(line) for line in re.split(r"[\r\n]+", text or "") if clean_text(line)]
    candidates = []
    seen = set()

    def add(value):
        value = clean_text(value)
        if not value or value in seen:
            return
        seen.add(value)
        candidates.append(value)

    for line in raw_lines:
        add(line)
    for index, line in enumerate(raw_lines):
        _price_text, price_value, _currency = parse_price(line)
        folded_line = fold_text(line)
        if price_value:
            add(" ".join(raw_lines[max(0, index - 3) : index + 1]))
        if WINE_TEXT_RE.search(folded_line):
            add(" ".join(raw_lines[index : min(len(raw_lines), index + 4)]))
            add(" ".join(raw_lines[max(0, index - 1) : min(len(raw_lines), index + 3)]))
    return candidates


def wine_line_score(line, watches):
    text = clean_text(line)
    if len(text) < 8 or len(text) > 260:
        return 0
    folded_text = fold_text(text)
    if BAD_LINE_RE.search(folded_text):
        return 0
    if re.fullmatch(r"(?:tasting\s+)?menu\s+(?:19|20)\d{2}", text, re.I):
        return 0
    if re.search(r"[_{}<>]|['\"]\s*:", text):
        return 0
    watch_hit = any(normalize_name(watch["keyword"]) in normalize_name(text) for watch in watches if watch.get("active", True))
    numbers = PRICE_NUMBER_RE.findall(text)
    price_text, price_value, currency = parse_price(text)
    has_vintage = bool(re.search(r"\b(19|20)\d{2}\b", text))
    has_wine_text = bool(WINE_TEXT_RE.search(folded_text))
    if not has_wine_text and not watch_hit:
        return 0
    score = 0
    if watch_hit:
        score += 5
    if has_vintage:
        score += 2
    if price_value:
        score += 3
    if currency:
        score += 2
    if has_wine_text:
        score += 3
    if len(numbers) >= 2:
        score += 1
    if re.fullmatch(r"(?:19|20)\d{2}", text.strip()):
        return 0
    has_price_context = bool(currency) or (has_vintage and len(numbers) >= 2)
    return score if score >= 5 and price_value and has_price_context else 0


def likely_wine_line(line, watches):
    return wine_line_score(line, watches) > 0


def source_confidence(url, source_type, text, lines, link_score):
    if not lines:
        return 0, "No parseable wine lines found."
    parsed = urlparse(url)
    haystack = fold_text(" ".join([parsed.netloc.lower(), parsed.path.lower(), text[:4000]]).replace("_", "-"))
    score = int(link_score or 0)
    core_count = sum(1 for line in lines if CORE_WINE_TEXT_RE.search(fold_text(line)))
    wine_text_count = sum(1 for line in lines if WINE_TEXT_RE.search(fold_text(line)))
    has_source_signal = source_url_signal(url, source_type, link_score)
    if not has_source_signal and core_count < 3:
        return score, "Candidate URL is not a wine-list page or file."
    if source_type == "pdf":
        score += 30
    if parsed.netloc.lower().startswith("wine.") or ".wine." in parsed.netloc.lower():
        score += 80
    if WINE_LINK_STRONG_RE.search(haystack):
        score += 40
    score += min(len(lines), 10) * 12
    if len(lines) >= 3:
        score += 30
    if sum(1 for line in lines if parse_price(line)[2]) >= 2:
        score += 20
    if core_count >= 1:
        score += 45
    if wine_text_count >= 2:
        score += 35
    if len(lines) < 2 and score < 180:
        return score, "Only one parseable wine line found; review required."
    if core_count == 0:
        return score, "No Burgundy, Champagne, or Bordeaux keywords found; review required."
    if score < 120:
        return score, "Candidate did not look enough like a wine list."
    return score, ""


def html_to_lines(html):
    text = re.sub(r"(?i)<\s*(br|p|div|li|tr|td|th|h[1-6])\b[^>]*>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = []
    for line in text.splitlines():
        cleaned = clean_text(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def save_wine_source(con, target, url, source_type, content, text, status="review", parser_status="review", line_count=0, error=""):
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
          last_checked_at, parser_status, line_count, last_error
        )
        values(?, ?, ?, ?, ?, ?, ?, current_timestamp, ?, ?, ?)
        on conflict(target_id, url) do update set
          source_type=excluded.source_type,
          status=excluded.status,
          content_path=excluded.content_path,
          text_path=excluded.text_path,
          checksum=excluded.checksum,
          last_checked_at=current_timestamp,
          parser_status=excluded.parser_status,
          line_count=excluded.line_count,
          last_error=excluded.last_error
        returning id
        """,
        (
            target_id,
            url,
            source_type,
            status,
            str(content_path.relative_to(ROOT)),
            str(text_path.relative_to(ROOT)),
            digest,
            parser_status,
            line_count,
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


def scan_wine_source(con, target, url, watches, link_score=0):
    try:
        content, content_type = fetch_text(url, timeout=6)
        source_type = "pdf" if "pdf" in content_type.lower() or urlparse(url).path.lower().endswith(".pdf") else "html"
        if source_type == "pdf":
            temp = DATA_DIR / "_temp.pdf"
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(content)
            text = pdf_text(temp)
        else:
            text = html_to_lines(content)
            if link_score >= 80:
                quick_lines = [line for line in candidate_text_lines(text) if likely_wine_line(line, watches)]
                if not quick_lines and os.environ.get("WHEREISKELLEY_RENDER_DYNAMIC") == "1":
                    rendered_text = render_page_text(url)
                    if rendered_text:
                        text = rendered_text
        lines = [clean_text(line) for line in candidate_text_lines(text) if likely_wine_line(line, watches)]
        confidence, review_reason = source_confidence(url, source_type, text or "", lines, link_score)
        verified = bool(lines) and not review_reason
        inserted_limit = min(len(lines), 1000) if verified else 0
        source_id = save_wine_source(
            con,
            target,
            url,
            source_type,
            content,
            text,
            status="found" if verified else "review",
            parser_status="parsed" if verified else "review",
            line_count=inserted_limit,
            error=review_reason,
        )
        inserted = 0
        if not verified:
            return 0, 0, review_reason
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
        if inserted != inserted_limit:
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
            links = discover_candidate_wine_links(target["website_url"], html, max_pages=18)
            if not links:
                con.execute(
                    "update restaurant_targets set status='no_wine_list', last_checked_at=current_timestamp where id=?",
                    (target["id"],),
                )
                continue
            target_sources = 0
            target_lines = 0
            review_reasons = []
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
                found, lines, error = scan_wine_source(con, target, link["url"], watches, link.get("score", 0))
                target_sources += found
                target_lines += lines
                if error:
                    review_reasons.append(error)
                    errors += 1
                if target_sources and (lines >= 10 or link.get("score", 0) >= 120):
                    break
            status = "found" if target_sources else "review"
            last_error = "" if target_sources else "; ".join(dict.fromkeys(review_reasons[:3]))
            con.execute(
                "update restaurant_targets set status=?, last_checked_at=current_timestamp, last_error=? where id=?",
                (status, last_error, target["id"]),
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
