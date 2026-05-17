import argparse
import json
import re
import sqlite3
import ssl
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "starwine.sqlite"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
PUBLIC_DATA_DIR = ROOT / "public" / "data"
SSL_CONTEXT = ssl._create_unverified_context()

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
            "https://guide.michelin.com/us/en/restaurants/1-star-michelin/2-stars-michelin/3-stars-michelin/page/1",
        ],
    },
}


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = []
        self._link = None
        self._script_type = ""
        self._script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._link = {"href": attrs.get("href"), "text": "", "attrs": attrs}
        if tag == "script":
            self._script_type = attrs.get("type", "")
            self._script = []

    def handle_data(self, data):
        if self._link is not None:
            self._link["text"] += data
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            self.links.append(self._link)
            self._link = None
        if tag == "script" and self._script is not None:
            self.scripts.append({"type": self._script_type, "text": "".join(self._script)})
            self._script = None
            self._script_type = ""


def now_sql():
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def clean_text(value):
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def target_key(name, city="", country=""):
    return "|".join([normalize_name(name), normalize_name(city), normalize_name(country)])


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    return con


def fetch_text(url, timeout=30):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with urlopen(Request(url, headers=headers), timeout=timeout, context=SSL_CONTEXT) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: expected a normal HTML page")
        data = response.read()
    return data.decode("utf-8", errors="replace")


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
        "websitesChecked": 0,
        "totalWebsites": 0,
        "wineListsFound": 0,
        "wineLinesFound": 0,
        "errors": 0,
    }
    current.update(payload)
    (PUBLIC_DATA_DIR / "guide-progress.json").write_text(
        json.dumps(current, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def init_db(con):
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


def source_id(con, code):
    return con.execute("select id from guide_sources where code=?", (code,)).fetchone()["id"]


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def extract_json_places(html, source_url):
    parser = LinkParser()
    parser.feed(html)
    places = []
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
        for obj in walk_json(payload):
            type_value = obj.get("@type") or obj.get("type") or obj.get("__typename") or ""
            type_text = " ".join(type_value) if isinstance(type_value, list) else str(type_value)
            name = obj.get("name") or obj.get("title") or obj.get("restaurantName")
            if not name or not re.search(r"restaurant|food|venue|place|card|item", type_text, re.I):
                continue
            address = obj.get("address") or {}
            if isinstance(address, dict):
                city = address.get("addressLocality") or address.get("city") or ""
                country = address.get("addressCountry") or address.get("country") or ""
                street = address.get("streetAddress") or ""
            else:
                city = obj.get("city") or ""
                country = obj.get("country") or ""
                street = clean_text(address)
            url = obj.get("url") or obj.get("sameAs") or obj.get("website") or ""
            if isinstance(url, list):
                url = url[0] if url else ""
            if url and str(url).startswith("/"):
                url = urljoin(source_url, url)
            places.append({
                "name": clean_text(name),
                "city": clean_text(city),
                "country": clean_text(country),
                "address": clean_text(street),
                "place_url": clean_text(url or source_url),
                "website_url": "",
                "rank": obj.get("position") or obj.get("rank"),
                "score": obj.get("score"),
            })
    return places


def extract_laliste_places(html, source_url):
    places = []
    pattern = re.compile(
        r'<a[^>]+place_id="(?P<place_id>[^"]+)"[^>]+href="(?P<href>[^"]+)"[^>]*>.*?'
        r'fs-list-field="name"[^>]*>(?P<name>.*?)</div>.*?'
        r'fs-list-field="city"[^>]*>(?P<city>.*?)</div>.*?'
        r'fs-list-field="country"[^>]*>(?P<country>.*?)</div>.*?'
        r'fs-list-field="score"[^>]*>(?P<score>.*?)</div>',
        re.I | re.S,
    )
    for index, match in enumerate(pattern.finditer(html), start=1):
        places.append({
            "name": clean_text(re.sub(r"<[^>]+>", " ", match.group("name"))),
            "city": clean_text(re.sub(r"<[^>]+>", " ", match.group("city"))),
            "country": clean_text(re.sub(r"<[^>]+>", " ", match.group("country"))),
            "address": "",
            "place_url": f"{source_url}#{match.group('place_id')}",
            "website_url": "",
            "rank": index,
            "score": clean_text(match.group("score")),
        })
    return places


def extract_worlds50best_places(html, source_url):
    places = []
    pattern = re.compile(
        r'<div class="list-item"[^>]*>.*?'
        r'<p class="rank[^"]*"[^>]*>(?P<rank>\d+)</p>.*?'
        r'<h2>(?P<name>.*?)</h2>\s*<p>(?P<city>.*?)</p>',
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        body = match.group(0)
        href_match = re.search(r'<a[^>]+href="([^"]+)"', body, re.I | re.S)
        rank = int(match.group("rank"))
        places.append({
            "name": clean_text(re.sub(r"<[^>]+>", " ", match.group("name"))),
            "city": clean_text(re.sub(r"<[^>]+>", " ", match.group("city"))),
            "country": "",
            "address": "",
            "place_url": urljoin(source_url, href_match.group(1)) if href_match else f"{source_url}#rank-{rank}",
            "website_url": "",
            "rank": rank,
            "score": None,
        })

    text = re.sub(r"<(br|p|h[1-6]|div|li)\b[^>]*>", "\n", html, flags=re.I)
    text = clean_text(re.sub(r"<[^>]+>", " ", text)).replace(" No.", "\nNo.")
    story_pattern = re.compile(r"\bNo\.(?P<rank>\d{1,3})\s+(?P<name>[^\n]+?)\s+(?P<city>[A-Z][^\n]+)")
    for match in story_pattern.finditer(text):
        name = re.sub(r"\s+-\s+.*$", "", match.group("name")).strip()
        city = match.group("city").strip()
        if not name or len(name) > 90 or len(city) > 80:
            continue
        rank = int(match.group("rank"))
        places.append({
            "name": clean_text(name),
            "city": clean_text(city),
            "country": "",
            "address": "",
            "place_url": f"{source_url}#rank-{rank}",
            "website_url": "",
            "rank": rank,
            "score": None,
        })
    return places


def extract_places(code, html, source_url):
    places = []
    if code == "laliste":
        places.extend(extract_laliste_places(html, source_url))
    elif code == "worlds50best":
        places.extend(extract_worlds50best_places(html, source_url))
    places.extend(extract_json_places(html, source_url))
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
    return unique


def upsert_place(con, source_code, source_url, place):
    sid = source_id(con, source_code)
    key = target_key(place["name"], place.get("city", ""), place.get("country", ""))
    cur = con.execute(
        """
        insert into guide_places(
          source_id, source_key, name, normalized_name, country, city, address,
          place_url, website_url, last_seen_at
        )
        values(?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        on conflict(source_id, source_key) do update set
          name=excluded.name,
          normalized_name=excluded.normalized_name,
          country=coalesce(nullif(excluded.country, ''), guide_places.country),
          city=coalesce(nullif(excluded.city, ''), guide_places.city),
          address=coalesce(nullif(excluded.address, ''), guide_places.address),
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


def upsert_target(con, source_code, place):
    key = target_key(place["name"], place.get("city", ""), place.get("country", ""))
    row = con.execute("select sources_json from restaurant_targets where normalized_key=?", (key,)).fetchone()
    sources = []
    if row:
        try:
            sources = json.loads(row["sources_json"] or "[]")
        except json.JSONDecodeError:
            sources = []
    if source_code not in sources:
        sources.append(source_code)
    con.execute(
        """
        insert into restaurant_targets(
          normalized_key, name, normalized_name, country, city, address,
          website_url, sources_json, source_count, priority, last_seen_at
        )
        values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        on conflict(normalized_key) do update set
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
            place.get("website_url", ""),
            json.dumps(sources),
            len(sources),
            max(1, len(sources)),
        ),
    )


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
    source_issues = []
    if run and run["notes"]:
        try:
            source_issues = json.loads(run["notes"])
        except json.JSONDecodeError:
            source_issues = [{"code": "collector", "message": run["notes"]}]
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
    (PUBLIC_DATA_DIR / "guide-status.json").write_text(
        json.dumps({"generatedAt": now_sql(), "counts": counts, "sourceCounts": source_counts, "sourceIssues": source_issues, "lastRun": dict(run) if run else None}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (PUBLIC_DATA_DIR / "guide-targets.json").write_text(
        json.dumps(targets, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def collect_targets(con, sources, max_source_items, run_id):
    collected = 0
    errors = 0
    source_seen = {code: 0 for code in sources}
    source_issues = []
    for code in sources:
        source = GUIDE_SOURCES[code]
        for url in source["urls"]:
            write_progress(
                runId=run_id,
                phase="reading_guides",
                source=code,
                currentUrl=url,
                targetsCollected=collected,
                errors=errors,
                message=f"Reading {source['name']} restaurant candidates.",
            )
            try:
                html = fetch_text(url)
            except Exception as exc:
                errors += 1
                source_issues.append({"code": code, "url": url, "message": str(exc)})
                write_progress(runId=run_id, phase="reading_guides", source=code, currentUrl=url, targetsCollected=collected, errors=errors, message=str(exc))
                continue
            places = extract_places(code, html, url)
            source_seen[code] += len(places)
            for place in places[:max_source_items or None]:
                collected += 1
                write_progress(
                    runId=run_id,
                    phase="saving_targets",
                    source=code,
                    currentTarget=place.get("name", ""),
                    currentUrl=place.get("place_url", "") or url,
                    targetsCollected=collected,
                    errors=errors,
                    message="Saving guide restaurant candidates.",
                )
                upsert_place(con, code, url, place)
                upsert_target(con, code, place)
                if collected % 25 == 0:
                    con.commit()
    for code, count in source_seen.items():
        if count == 0:
            source_issues.append({
                "code": code,
                "url": GUIDE_SOURCES[code]["urls"][0],
                "message": "No parseable restaurant cards were found. The source may be blocked, challenged, or rendered only after browser scripts.",
            })
    return collected, errors, source_issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="michelin,laliste,worlds50best")
    parser.add_argument("--max-source-items", type=int, default=0, help="Per source URL. 0 means all.")
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    sources = [item.strip() for item in args.sources.split(",") if item.strip() in GUIDE_SOURCES]
    with connect() as con:
        init_db(con)
        cur = con.execute(
            "insert into guide_collection_runs(started_at, status, sources_requested) values(?, 'running', ?)",
            (now_sql(), ",".join(sources)),
        )
        run_id = cur.lastrowid
        try:
            collected, errors, source_issues = collect_targets(con, sources, args.max_source_items, run_id)
            target_total = con.execute("select count(*) from restaurant_targets").fetchone()[0]
            notes = json.dumps(source_issues, ensure_ascii=False) if source_issues else None
            con.execute(
                """
                update guide_collection_runs
                set finished_at=?, status='completed', target_count=?, websites_checked=0,
                    wine_lists_found=0, wine_lines_found=0, errors=?, notes=?
                where id=?
                """,
                (now_sql(), target_total, errors, notes, run_id),
            )
            write_progress(runId=run_id, status="completed", phase="completed", targetsCollected=target_total, errors=errors, message="Guide target collection completed.")
        finally:
            export_status(con, run_id)
            con.commit()
        print(f"targets={target_total} processed={collected} websites=0 wine_lists=0 wine_lines=0 errors={errors}")


if __name__ == "__main__":
    main()
