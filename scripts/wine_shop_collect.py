#!/usr/bin/env python3
import argparse
import base64
import csv
import hashlib
import heapq
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import Request, build_opener
from urllib.robotparser import RobotFileParser


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wine_shop_db import SHOP_DB_PATH, PROGRESS_PATH, connect_shop, content_hash, ensure_shop_db, fold_text, upsert_product, utc_now
from country_codes import normalize_country_code


USER_AGENT = os.environ.get(
    "WHEREISKELLEY_SHOP_USER_AGENT",
    "WhereIsKelleyWineInventory/1.0 (+personal wine availability index; contact via repository)",
)
WINE_SEARCHER_ROOT = "https://www.wine-searcher.com"
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
PROFILE_BLOCK_MARKERS = (
    "captcha", "access denied", "temporarily blocked", "too many requests", "verify you are human",
    "press and hold", "prove you are human", "human verification", "px-captcha", "perimeterx",
    "로봇이 아니라 사람", "길게 눌러",
)
SOCIAL_DOMAINS = (
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com", "youtube.com",
    "pinterest.com", "tiktok.com", "google.com", "apple.com",
)
WINE_PATH_WORDS = (
    "wine", "wines", "winelist", "wine-list", "wine_list", "vin", "vins", "vino", "vini",
    "wein", "wijn", "drinks", "beverage", "cellar", "bottle", "catalog", "catalogue",
    "price-list", "pricelist", "carta-vini", "carte-des-vins", "shop-wine",
)
EDITORIAL_PATH_WORDS = (
    "blog", "news", "event", "events", "journal", "story", "stories", "article",
    "articles", "tasting", "tastings", "press", "recipe", "recipes",
)
CATALOG_PATH_WORDS = (
    "wine-list", "winelist", "wines", "shop", "store", "products", "collections",
    "catalog", "catalogue", "inventory", "price-list", "pricelist", "shop-wine",
)
COMMERCE_TEXT_WORDS = (
    "add to cart", "add to basket", "buy now", "shop now", "quick add", "checkout",
    "in stock", "out of stock", "available for purchase",
)
WINE_DOCUMENT_WORDS = (
    "wine list", "wine menu", "wine selection", "wine catalogue", "wine catalog",
    "wine price list", "carte des vins", "carta dei vini", "carta de vinos",
    "weinliste", "weinkarte", "wijnkaart", "vinkort", "vinlista",
)
NON_WINE_DOCUMENT_WORDS = (
    "horse race", "horse racing", "raceway", "racetrack", "race results",
    "race result", "post position", "starting gate", "purse", "trotter",
    "trotting", "pacing", "trainer", "driver", "finish time", "race time",
)
WINE_EVIDENCE = (
    "burgundy", "bourgogne", "burgund", "champagne", "bordeaux", "chablis", "beaujolais",
    "moulin a vent", "morgon", "fleurie", "cote de brouilly", "saint amour",
    "vosne", "romanee", "romanée", "gevrey", "chambertin", "chambolle", "musigny", "pommard",
    "puligny", "chassagne", "meursault", "corton", "montrachet", "volnay", "nuits saint georges",
    "krug", "dom perignon", "dom pérignon", "bollinger", "salon", "selosse", "rayas",
    "cabernet", "pinot noir", "chardonnay", "riesling", "syrah", "merlot", "sauvignon blanc",
)
PRICE_RE = re.compile(
    r"(?:(USD|EUR|GBP|HKD|JPY|KRW|AUD|CAD|SGD|CHF|CNY|RMB|DKK|NOK|SEK|NZD|ZAR|AED|HK\$|US\$|A\$|C\$|S\$|NT\$|€|£|\$|¥|₩)\s*)?"
    r"([0-9]{1,3}(?:[,.\s][0-9]{3})+|[0-9]{1,6}(?:[,.][0-9]{2})?)"
    r"\s*(USD|EUR|GBP|HKD|JPY|KRW|AUD|CAD|SGD|CHF|CNY|RMB|DKK|NOK|SEK|NZD|ZAR|AED|HK\$|US\$|A\$|C\$|S\$|NT\$|€|£|\$|¥|₩)?",
    re.I,
)
VINTAGE_RE = re.compile(r"\b(?:19[4-9]\d|20[0-3]\d)\b")
SIZE_RE = re.compile(r"\b(375|500|700|750|1000|1500|3000|6000)\s*ml\b", re.I)
CURRENCY_SYMBOLS = {
    "€": "EUR", "£": "GBP", "$": "USD", "US$": "USD", "HK$": "HKD",
    "A$": "AUD", "C$": "CAD", "S$": "SGD", "NT$": "TWD", "¥": "JPY",
    "₩": "KRW", "RMB": "CNY",
}


class LinkTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.text = []
        self.title = []
        self.headings = []
        self.meta = {}
        self.canonical = ""
        self.json_ld = []
        self._anchor_href = ""
        self._anchor_text = []
        self._in_title = False
        self._in_heading = False
        self._in_json = False
        self._json_parts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        tag = tag.lower()
        if tag == "a":
            self._anchor_href = values.get("href", "")
            self._anchor_text = []
        elif tag == "title":
            self._in_title = True
        elif tag in {"h1", "h2"}:
            self._in_heading = True
        elif tag == "meta":
            key = values.get("property") or values.get("name") or ""
            if key and values.get("content"):
                self.meta[key.lower()] = values["content"]
        elif tag == "link" and "canonical" in values.get("rel", "").lower():
            self.canonical = values.get("href", "")
        elif tag == "script" and "ld+json" in values.get("type", "").lower():
            self._in_json = True
            self._json_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self._anchor_href:
            self.links.append((self._anchor_href, " ".join(self._anchor_text).strip()))
            self._anchor_href = ""
            self._anchor_text = []
        elif tag == "title":
            self._in_title = False
        elif tag in {"h1", "h2"}:
            self._in_heading = False
        elif tag == "script" and self._in_json:
            self.json_ld.append("".join(self._json_parts))
            self._in_json = False
            self._json_parts = []

    def handle_data(self, data):
        clean = " ".join(data.split())
        if clean:
            self.text.append(clean)
            if self._anchor_href:
                self._anchor_text.append(clean)
            if self._in_title:
                self.title.append(clean)
            if self._in_heading:
                self.headings.append(clean)
        if self._in_json:
            self._json_parts.append(data)


class AdaptiveLimiter:
    def __init__(self, requests_per_second=4.0, minimum=0.15, maximum=8.0):
        self.rate = max(minimum, min(float(requests_per_second), maximum))
        self.minimum = minimum
        self.maximum = maximum
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.successes = 0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + (1.0 / self.rate)
        if delay:
            time.sleep(delay)

    def result(self, status):
        with self.lock:
            if status in {403, 429, 503}:
                self.rate = max(self.minimum, self.rate * 0.5)
                self.successes = 0
            elif 200 <= status < 400:
                self.successes += 1
                if self.successes >= 200:
                    self.rate = min(self.maximum, self.rate * 1.1)
                    self.successes = 0


class DomainSlots:
    def __init__(self, per_domain=2):
        self.per_domain = max(1, int(per_domain))
        self.lock = threading.Lock()
        self.slots = {}

    def for_url(self, url):
        domain = (urlparse(url).hostname or "").lower()
        with self.lock:
            return self.slots.setdefault(domain, threading.BoundedSemaphore(self.per_domain))


class RobotsPolicy:
    def __init__(self, domain_slots=None):
        self.domain_slots = domain_slots
        self.lock = threading.Lock()
        self.cache = {}

    def allowed(self, url):
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        missing = object()
        with self.lock:
            cached = self.cache.get(origin, missing)
        if cached is missing:
            robots_url = urljoin(origin, "/robots.txt")
            response = fetch_url(
                robots_url,
                timeout=10,
                domain_slots=self.domain_slots,
                obey_robots=False,
            )
            parser = RobotFileParser()
            parser.set_url(robots_url)
            if response["status"] == 200:
                parser.parse(response["body"].decode("utf-8", errors="replace").splitlines())
                policy = parser
            else:
                policy = True
            with self.lock:
                cached = self.cache.setdefault(origin, policy)
        return True if cached is True else cached.can_fetch(USER_AGENT, url)


class ScanBlocked(RuntimeError):
    pass


class AccessCircuit:
    def __init__(self, threshold=20):
        self.threshold = max(1, int(threshold))
        self.lock = threading.Lock()
        self.consecutive_blocks = 0
        self.reason = ""

    def blocked(self):
        with self.lock:
            return bool(self.reason)

    def record(self, response):
        status = int(response.get("status") or 0)
        error = str(response.get("error") or "").lower()
        denied = status in {401, 403, 429} or "blocking/interstitial" in error
        with self.lock:
            if denied:
                self.consecutive_blocks += 1
            elif status in {200, 404, 410}:
                self.consecutive_blocks = 0
            if self.consecutive_blocks >= self.threshold and not self.reason:
                self.reason = (
                    f"Wine-Searcher blocked {self.consecutive_blocks} consecutive public profile requests "
                    f"(last HTTP status: {status or 'unknown'}). The scan stopped without bypassing the block."
                )
            return self.reason


def atomic_progress(payload):
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    complete = {"generatedAt": utc_now(), **payload}
    temp = PROGRESS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(complete, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(PROGRESS_PATH)


def fetch_url(
    url, timeout=20, limiter=None, headers=None, domain_slots=None, robots=None,
    obey_robots=True, method="GET", data=None,
):
    if obey_robots and robots is not None and not robots.allowed(url):
        return {
            "status": 0,
            "url": url,
            "content_type": "",
            "headers": {},
            "body": b"",
            "error": "Blocked by robots.txt.",
        }
    if limiter:
        limiter.wait()
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json,application/pdf,text/csv,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8",
    }
    request_headers.update(headers or {})
    request = Request(url, headers=request_headers, data=data, method=method)
    status = 0
    slot = domain_slots.for_url(url) if domain_slots else None
    try:
        if slot:
            slot.acquire()
        try:
            with build_opener().open(request, timeout=timeout) as response:
                status = int(response.status or 200)
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError("Response exceeded the 25 MB collection limit.")
                result = {
                    "status": status,
                    "url": response.geturl(),
                    "content_type": response.headers.get_content_type() or "application/octet-stream",
                    "headers": dict(response.headers.items()),
                    "body": body,
                }
        finally:
            if slot:
                slot.release()
    except HTTPError as exc:
        status = int(exc.code or 0)
        result = {"status": status, "url": exc.geturl() or url, "content_type": "", "headers": {}, "body": b"", "error": str(exc)}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        result = {"status": status, "url": url, "content_type": "", "headers": {}, "body": b"", "error": str(exc)}
    if limiter:
        limiter.result(result["status"])
    return result


def post_json(url, payload, timeout=25, headers=None, domain_slots=None):
    request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    request_headers.update(headers or {})
    return fetch_url(
        url,
        timeout=timeout,
        headers=request_headers,
        domain_slots=domain_slots,
        obey_robots=False,
        method="POST",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )


def iter_json_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_nodes(child)


def parse_json_ld(parser):
    nodes = []
    for raw in parser.json_ld:
        try:
            parsed = json.loads(raw.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        nodes.extend(iter_json_nodes(parsed))
    return nodes


def external_website(links, base_url):
    base_host = (urlparse(base_url).hostname or "").lower()
    candidates = []
    for href, label in links:
        absolute = urljoin(base_url, unescape(href)).strip()
        parsed = urlparse(absolute)
        score = 0
        if "redirect" in parsed.path or "out" in parsed.path:
            query = parse_qs(parsed.query)
            for key in ("url", "u", "target", "redirect"):
                if query.get(key):
                    candidate = unquote(query[key][0])
                    if candidate.startswith(("http://", "https://")):
                        absolute = candidate
                        parsed = urlparse(absolute)
                        score += 2
                        break
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host or host == base_host or host.endswith("wine-searcher.com"):
            continue
        if any(host == item or host.endswith("." + item) for item in SOCIAL_DOMAINS):
            continue
        text = fold_text(f"{label} {absolute}")
        if any(word in text for word in ("website", "visit", "merchant", "store", "shop")):
            score += 5
        candidates.append((score, len(parsed.path), absolute))
    return max(candidates, default=(0, 0, ""))[2]


def address_parts(value):
    if not isinstance(value, dict):
        return "", "", ""
    address = ", ".join(str(value.get(key) or "").strip() for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry") if value.get(key))
    country_value = value.get("addressCountry") or ""
    if isinstance(country_value, dict):
        country_value = country_value.get("name") or ""
    return address, str(value.get("addressLocality") or ""), str(country_value)


def parse_merchant_profile(html, requested_url, final_url=""):
    parser = LinkTextParser()
    parser.feed(html)
    nodes = parse_json_ld(parser)
    business = next((node for node in nodes if str(node.get("@type", "")).lower() in {"store", "liquorstore", "localbusiness", "organization"}), {})
    title = " ".join(parser.title).strip()
    name = str(business.get("name") or (parser.headings[0] if parser.headings else "") or title).strip()
    name = re.sub(r"\s*[|\-–]\s*Wine-Searcher.*$", "", name, flags=re.I).strip()
    text = " ".join(parser.text)
    folded = fold_text(text[:250000])
    if any(marker in folded for marker in PROFILE_BLOCK_MARKERS):
        raise RuntimeError("Wine-Searcher returned a blocking/interstitial page.")
    if not name or name.lower() in {"wine-searcher", "page not found", "not found"}:
        raise LookupError("Merchant profile was not found.")
    address, city, country = address_parts(business.get("address"))
    geo = business.get("geo") if isinstance(business.get("geo"), dict) else {}
    website = str(business.get("url") or "").strip()
    if website and (urlparse(website).hostname or "").endswith("wine-searcher.com"):
        website = ""
    website = website or external_website(parser.links, final_url or requested_url)
    item_match = re.search(r"([0-9][0-9,\s]*)\s+(?:wines?|offers?|prices?|products?)\b", text, re.I)
    canonical = parser.canonical or final_url or requested_url
    return {
        "wine_searcher_url": canonical,
        "name": name,
        "normalized_name": fold_text(name),
        "merchant_type": str(business.get("@type") or "Wine Shop"),
        "description": str(business.get("description") or parser.meta.get("description") or "").strip(),
        "website_url": website,
        "website_domain": (urlparse(website).hostname or "").lower(),
        "country": country,
        "city": city,
        "address": address,
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "phone": str(business.get("telephone") or ""),
        "wine_searcher_item_count": int(re.sub(r"\D", "", item_match.group(1))) if item_match else None,
        "raw_hash": hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest(),
    }


def profile_job(merchant_id, limiter, domain_slots=None, robots=None, circuit=None):
    url = f"{WINE_SEARCHER_ROOT}/merchant/{merchant_id}"
    if circuit and circuit.blocked():
        return merchant_id, "blocked", {"status": 0, "url": url, "error": circuit.reason}, None
    response = fetch_url(
        url,
        timeout=18,
        limiter=limiter,
        domain_slots=domain_slots,
        robots=robots,
    )
    if circuit:
        circuit.record(response)
    if response["status"] in {404, 410}:
        return merchant_id, "missing", response, None
    if response["status"] != 200:
        return merchant_id, "error", response, None
    html = response["body"].decode("utf-8", errors="replace")
    try:
        profile = parse_merchant_profile(html, url, response["url"])
    except LookupError as exc:
        response["error"] = str(exc)
        return merchant_id, "missing", response, None
    except Exception as exc:
        response["error"] = str(exc)
        return merchant_id, "error", response, None
    return merchant_id, "found", response, profile


def save_profile_result(con, result):
    merchant_id, status, response, profile = result
    error = response.get("error") or ""
    con.execute(
        """
        insert into merchant_scan_ids(merchant_id,status,http_status,canonical_url,error,checked_at)
        values(?,?,?,?,?,?)
        on conflict(merchant_id) do update set status=excluded.status,http_status=excluded.http_status,
          canonical_url=excluded.canonical_url,error=excluded.error,checked_at=excluded.checked_at
        """,
        (merchant_id, status, response.get("status"), response.get("url"), error, utc_now()),
    )
    if not profile:
        return False
    raw_country = (profile.get("country") or "").strip()
    country_code = normalize_country_code(
        raw_country,
        city=profile.get("city"),
        address=profile.get("address"),
    )
    con.execute(
        """
        insert into merchants(
          wine_searcher_id,wine_searcher_url,name,normalized_name,merchant_type,description,
          website_url,website_domain,country,country_raw,city,address,latitude,longitude,phone,
          wine_searcher_item_count,profile_status,profile_error,first_seen_at,last_seen_at,
          last_profile_checked_at,active,raw_hash
        ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        on conflict(wine_searcher_id) do update set
          wine_searcher_url=excluded.wine_searcher_url,name=excluded.name,
          normalized_name=excluded.normalized_name,merchant_type=excluded.merchant_type,
          description=excluded.description,
          website_url=coalesce(nullif(excluded.website_url,''),merchants.website_url),
          website_domain=coalesce(nullif(excluded.website_domain,''),merchants.website_domain),
          country=coalesce(nullif(excluded.country,''),merchants.country),
          country_raw=coalesce(nullif(excluded.country_raw,''),merchants.country_raw),
          city=coalesce(nullif(excluded.city,''),merchants.city),
          address=coalesce(nullif(excluded.address,''),merchants.address),
          latitude=coalesce(excluded.latitude,merchants.latitude),
          longitude=coalesce(excluded.longitude,merchants.longitude),
          phone=coalesce(nullif(excluded.phone,''),merchants.phone),
          wine_searcher_item_count=coalesce(excluded.wine_searcher_item_count,merchants.wine_searcher_item_count),
          profile_status='found',profile_error='',last_seen_at=excluded.last_seen_at,
          last_profile_checked_at=excluded.last_profile_checked_at,active=1,raw_hash=excluded.raw_hash
        """,
        (
            merchant_id, profile["wine_searcher_url"], profile["name"], profile["normalized_name"],
            profile["merchant_type"], profile["description"], profile["website_url"],
            profile["website_domain"], country_code or None, raw_country or None,
            profile["city"], profile["address"],
            profile["latitude"], profile["longitude"], profile["phone"],
            profile["wine_searcher_item_count"], "found", "", utc_now(), utc_now(), utc_now(),
            1, profile["raw_hash"],
        ),
    )
    return True


def run_merchant_scan(args):
    ensure_shop_db(args.db)
    con = connect_shop(args.db)
    run_id = con.execute(
        "insert into merchant_scan_runs(phase,status,range_start,range_end) values('merchant_scan','running',?,?)",
        (args.start, args.end),
    ).lastrowid
    con.commit()
    limiter = AdaptiveLimiter(args.rps, maximum=args.max_rps)
    circuit = AccessCircuit(args.block_threshold)
    domain_slots = DomainSlots(min(8, args.workers))
    robots = RobotsPolicy(domain_slots)
    if not robots.allowed(f"{WINE_SEARCHER_ROOT}/merchant/{args.start}"):
        message = "Wine-Searcher robots.txt does not permit the merchant profile scan."
        con.execute(
            "update merchant_scan_runs set status='blocked',finished_at=?,errors=1 where id=?",
            (utc_now(), run_id),
        )
        con.commit()
        atomic_progress({
            "status": "blocked", "phase": "merchant_scan", "runId": run_id,
            "checked": 0, "found": 0, "errors": 1, "message": message,
        })
        con.close()
        raise RuntimeError(message)
    total_range = max(0, args.end - args.start + 1)
    completed_before = 0
    if args.resume:
        completed_before = con.execute(
            "select count(*) from merchant_scan_ids where merchant_id between ? and ? and status in ('found','missing')",
            (args.start, args.end),
        ).fetchone()[0]
    total_pending = max(0, total_range - completed_before)
    checked = found = errors = 0
    started = time.monotonic()
    atomic_progress({
        "status": "running", "phase": "merchant_scan",
        "message": "Scanning Wine-Searcher merchant profiles.", "runId": run_id,
        "checked": 0, "total": total_pending, "remaining": total_pending,
        "found": 0, "errors": 0, "rangeStart": args.start, "rangeEnd": args.end,
        "requestsPerSecond": round(limiter.rate, 2), "elapsedSeconds": 0,
    })
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            cursor = args.start
            while cursor <= args.end:
                stop = min(args.end, cursor + args.batch_size - 1)
                ids = list(range(cursor, stop + 1))
                if args.resume:
                    done = {
                        row[0] for row in con.execute(
                            "select merchant_id from merchant_scan_ids where merchant_id between ? and ? and status in ('found','missing')",
                            (cursor, stop),
                        )
                    }
                    ids = [merchant_id for merchant_id in ids if merchant_id not in done]
                futures = [
                    pool.submit(profile_job, merchant_id, limiter, domain_slots, robots, circuit)
                    for merchant_id in ids
                ]
                for future in as_completed(futures):
                    result = future.result()
                    if result[1] == "blocked":
                        continue
                    checked += 1
                    if save_profile_result(con, result):
                        found += 1
                    elif result[1] == "error":
                        errors += 1
                    if checked % 50 == 0:
                        con.commit()
                        elapsed = max(0.001, time.monotonic() - started)
                        remaining = max(0, total_pending - checked)
                        atomic_progress({
                            "status": "running", "phase": "merchant_scan", "message": "Scanning Wine-Searcher merchant profiles.",
                            "runId": run_id, "checked": checked, "found": found, "errors": errors,
                            "total": total_pending, "remaining": remaining,
                            "rangeStart": args.start, "rangeEnd": args.end, "currentMerchantId": result[0],
                            "requestsPerSecond": round(limiter.rate, 2), "elapsedSeconds": int(elapsed),
                            "estimatedRemainingSeconds": int(remaining / max(0.01, checked / elapsed)),
                        })
                con.commit()
                if circuit.blocked():
                    raise ScanBlocked(circuit.reason)
                cursor = stop + 1
        con.execute(
            "update merchant_scan_runs set status='done',finished_at=?,checked=?,found=?,errors=? where id=?",
            (utc_now(), checked, found, errors, run_id),
        )
        con.commit()
        atomic_progress({
            "status": "done", "phase": "merchant_scan", "runId": run_id,
            "checked": checked, "total": total_pending, "remaining": 0,
            "found": found, "errors": errors,
        })
    except ScanBlocked as exc:
        con.execute(
            "update merchant_scan_runs set status='blocked',finished_at=?,checked=?,found=?,errors=? where id=?",
            (utc_now(), checked, found, errors, run_id),
        )
        con.commit()
        atomic_progress({
            "status": "blocked", "phase": "merchant_scan", "runId": run_id,
            "checked": checked, "total": total_pending, "remaining": max(0, total_pending - checked),
            "found": found, "errors": errors, "message": str(exc),
        })
    except KeyboardInterrupt:
        con.execute("update merchant_scan_runs set status='stopped',finished_at=?,checked=?,found=?,errors=? where id=?", (utc_now(), checked, found, errors, run_id))
        con.commit()
        atomic_progress({"status": "stopped", "phase": "merchant_scan", "runId": run_id, "checked": checked, "found": found, "errors": errors})
        raise
    finally:
        con.close()


def currency_code(value):
    text = str(value or "").strip().upper()
    return CURRENCY_SYMBOLS.get(text, text)


def number_value(value):
    if value is None:
        return None
    text = re.sub(r"[^0-9,.]", "", str(value)).strip(".,")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") == 1 and len(text.rsplit(",", 1)[1]) == 2:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "").replace(" ", "")
    try:
        return float(text)
    except ValueError:
        return None


def price_match_from_text(text):
    vintage_spans = [match.span() for match in VINTAGE_RE.finditer(text)]
    size_spans = [match.span() for match in SIZE_RE.finditer(text)]
    for match in reversed(list(PRICE_RE.finditer(text))):
        start, end = match.span(2)
        before_currency = (match.group(1) or "").strip()
        after_currency = (match.group(3) or "").strip()
        has_currency = bool(before_currency or after_currency)
        if re.match(r"\s*%", text[match.end():]):
            continue
        if not has_currency and any(start < span_end and end > span_start for span_start, span_end in vintage_spans):
            continue
        if not has_currency and any(start < span_end and end > span_start for span_start, span_end in size_spans):
            continue
        return match
    return None


def product_from_text(text, source_url, source_key="", structured=False, trusted_catalog=False):
    clean = " ".join(str(text or "").split()).strip()
    if len(clean) < 5:
        return None
    folded = fold_text(clean)
    if not trusted_catalog and not any(term in folded for term in WINE_EVIDENCE):
        return None
    if not structured:
        # A single catalogue row is compact. Long sentence-shaped blocks are
        # usually editorial copy where a temperature, year, or address was
        # mistaken for a price.
        if len(clean) > 240 or len(clean.split()) > 38:
            return None
        if any(marker in folded for marker in (
            "window.", "document.", "function(", "webpack", "application/ld+json",
            "schema.org", "javascript:",
        )):
            return None
    price_match = price_match_from_text(clean)
    vintage_match = VINTAGE_RE.search(clean)
    if not structured and not price_match and not vintage_match:
        return None
    if not structured and not price_match and len(clean) > 180:
        return None
    if (
        not structured
        and not price_match
        and len(clean.split()) >= 12
        and clean.endswith((".", "!", "?"))
    ):
        return None
    price_value = number_value(price_match.group(2)) if price_match else None
    currency = currency_code((price_match.group(1) or price_match.group(3)) if price_match else "")
    vintage = vintage_match.group(0) if vintage_match else ""
    size_match = SIZE_RE.search(clean)
    return {
        "source_key": source_key or content_hash(clean),
        "source_url": source_url,
        "raw_name": clean[:500],
        "wine_name": clean[:500],
        "vintage": vintage,
        "size_ml": int(size_match.group(1)) if size_match else None,
        "price_value": price_value,
        "currency": currency,
        "price_text": price_match.group(0).strip() if price_match else "",
        "availability": "listed",
        "raw_text": clean[:4000],
    }


def corksy_config_from_html(html):
    folded = fold_text(html[:250000])
    if "corksy" not in folded and "data-widget-config" not in folded:
        return None
    app_match = re.search(r"ExternalUid\s*:\s*['\"]([^'\"]+)['\"]", html, re.I)
    if not app_match:
        return None
    collection_ids = []
    for encoded in re.findall(r"data-widget-config\s*=\s*['\"]([^'\"]+)['\"]", html, re.I):
        try:
            raw = unescape(encoded).strip()
            raw += "=" * (-len(raw) % 4)
            config = json.loads(base64.b64decode(raw).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        collection_id = str(config.get("collectionId") or "").strip()
        if collection_id and collection_id not in collection_ids:
            collection_ids.append(collection_id)
    if not collection_ids:
        return None
    return {"app_key": app_match.group(1), "collection_ids": collection_ids}


def corksy_products_from_payload(payload, catalog_url):
    search = ((payload.get("data") or {}).get("searchVariantsV2") or {})
    products = []
    for row in search.get("nodes") or []:
        name = str(row.get("productName") or "").strip()
        product_nodes = ((row.get("product") or {}).get("nodes") or [])
        variants = (product_nodes[0].get("variants") or {}).get("nodes") if product_nodes else []
        variants = variants or [{}]
        for variant in variants:
            variant_name = str(variant.get("name") or "").strip()
            compact_name = re.sub(r"\W+", "", fold_text(name))
            compact_variant = re.sub(r"\W+", "", fold_text(variant_name))
            include_variant = (
                variant_name
                and variant_name.lower() != "default"
                and compact_variant not in compact_name
            )
            display_name = " ".join(
                value for value in (name, variant_name if include_variant else "") if value
            )
            slug = str(variant.get("pageItemUrl") or row.get("pageItemUrl") or "").strip("/")
            product_url = urljoin(catalog_url, f"/wine/{slug}") if slug else catalog_url
            product = product_from_text(
                display_name,
                product_url,
                str(variant.get("id") or row.get("productId") or content_hash(display_name)),
                structured=True,
                trusted_catalog=True,
            )
            if not product:
                continue
            regular_price = number_value(variant.get("price"))
            discount_price = number_value(variant.get("discountPrice"))
            price = discount_price if discount_price and discount_price > 0 else regular_price
            product["price_value"] = price
            product["currency"] = "USD"
            product["price_text"] = f"USD {price:g}" if price is not None else ""
            available = number_value(variant.get("available"))
            product["availability"] = "in_stock" if available is None or available > 0 else "out_of_stock"
            products.append(product)
    return products, int(search.get("totalCount") or len(products))


def corksy_products(catalog_url, html, domain_slots=None, config=None):
    config = config or corksy_config_from_html(html)
    if not config:
        return []
    login = post_json(
        "https://api.gocorksy.com/users/v1/auth/app/login",
        {"appKey": config["app_key"]},
        domain_slots=domain_slots,
    )
    if login["status"] != 200:
        return []
    try:
        token = json.loads(login["body"].decode("utf-8"))["accessToken"]
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    query = """
      query Search($offset:Int,$first:Int,$pCollectionId:UUID) {
        searchVariantsV2(first:$first,offset:$offset,pCollectionId:$pCollectionId) {
          nodes {
            productId productName pageItemUrl
            product { nodes { variants(filter:{deletedAt:{isNull:true}}) {
              nodes { id price discountPrice pageItemUrl name available:shipAvailableForEcom }
            } } }
          }
          totalCount
        }
      }
    """
    products = []
    for collection_id in config["collection_ids"]:
        offset = 0
        while True:
            response = post_json(
                "https://graphql.gocorksy.com/graphql",
                {"query": query, "variables": {"first": 100, "offset": offset, "pCollectionId": collection_id}},
                headers={"Authorization": f"Bearer {token}"},
                domain_slots=domain_slots,
            )
            if response["status"] != 200:
                break
            try:
                payload = json.loads(response["body"].decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                break
            page_products, total = corksy_products_from_payload(payload, catalog_url)
            products.extend(page_products)
            offset += 100
            if offset >= total or not page_products:
                break
    return products


def structured_products(nodes, page_url):
    products = []
    for node in nodes:
        node_type = node.get("@type")
        types = {str(value).lower() for value in (node_type if isinstance(node_type, list) else [node_type])}
        if "product" not in types:
            continue
        name = str(node.get("name") or "").strip()
        description = str(node.get("description") or "").strip()
        if not any(term in fold_text(f"{name} {description}") for term in WINE_EVIDENCE):
            continue
        offers = node.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        product = product_from_text(
            f"{name} {description}",
            str(node.get("url") or page_url),
            str(node.get("sku") or node.get("productID") or node.get("url") or content_hash(name)),
            structured=True,
        )
        if not product:
            continue
        if isinstance(offers, dict):
            product["price_value"] = number_value(offers.get("price") or offers.get("lowPrice"))
            product["currency"] = currency_code(offers.get("priceCurrency"))
            product["price_text"] = " ".join(filter(None, (str(offers.get("priceCurrency") or ""), str(offers.get("price") or offers.get("lowPrice") or "")))).strip()
            product["availability"] = str(offers.get("availability") or "listed").rsplit("/", 1)[-1]
            product["source_url"] = str(offers.get("url") or product["source_url"])
        products.append(product)
    return products


def shopify_products(base_url, domain_slots=None, robots=None):
    products = []
    for page in range(1, 101):
        response = fetch_url(
            urljoin(base_url, f"/products.json?limit=250&page={page}"),
            timeout=25,
            domain_slots=domain_slots,
            robots=robots,
        )
        if response["status"] != 200 or "json" not in response["content_type"]:
            break
        try:
            rows = json.loads(response["body"].decode("utf-8", errors="replace")).get("products") or []
        except (json.JSONDecodeError, AttributeError):
            break
        if not rows:
            break
        for row in rows:
            title = str(row.get("title") or "")
            body = re.sub(r"<[^>]+>", " ", str(row.get("body_html") or ""))
            for variant in row.get("variants") or [{}]:
                text = " ".join(filter(None, (title, str(variant.get("title") or ""), body)))
                product = product_from_text(
                    text,
                    urljoin(base_url, f"/products/{row.get('handle') or ''}"),
                    str(variant.get("id") or row.get("id")),
                    structured=True,
                )
                if product:
                    product["price_value"] = number_value(variant.get("price"))
                    product["price_text"] = str(variant.get("price") or "")
                    product["availability"] = "in_stock" if variant.get("available", True) else "out_of_stock"
                    products.append(product)
        if len(rows) < 250:
            break
    return products


def woo_products(base_url, domain_slots=None, robots=None):
    products = []
    for page in range(1, 101):
        endpoint = urljoin(base_url, f"/wp-json/wc/store/v1/products?per_page=100&page={page}")
        response = fetch_url(endpoint, timeout=25, domain_slots=domain_slots, robots=robots)
        if response["status"] != 200 or "json" not in response["content_type"]:
            break
        try:
            rows = json.loads(response["body"].decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            break
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            text = " ".join(filter(None, (str(row.get("name") or ""), re.sub(r"<[^>]+>", " ", str(row.get("description") or "")))))
            product = product_from_text(
                text,
                str(row.get("permalink") or base_url),
                str(row.get("id") or content_hash(text)),
                structured=True,
            )
            if product:
                prices = row.get("prices") or {}
                minor = int(prices.get("currency_minor_unit") or 2)
                raw_price = number_value(prices.get("price"))
                product["price_value"] = raw_price / (10 ** minor) if raw_price is not None else None
                product["currency"] = currency_code(prices.get("currency_code") or prices.get("currency_symbol"))
                product["price_text"] = f"{product['currency']} {product['price_value']}" if product["price_value"] is not None else ""
                product["availability"] = "in_stock" if row.get("is_in_stock") else "out_of_stock"
                products.append(product)
        if len(rows) < 100:
            break
    return products


def visible_lines(parser):
    current = []
    for text in parser.text:
        current.append(text)
        joined = " ".join(current)
        if len(joined) >= 80 or PRICE_RE.search(joined):
            yield joined
            current = []
    if current:
        yield " ".join(current)


def parse_pdf_products(body, source_url):
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return [], "pdf extraction failed"
    products = []
    for line in text.splitlines():
        product = product_from_text(line, source_url)
        if product:
            products.append(product)
    folded = fold_text(text)
    path = fold_text(unquote(urlparse(source_url).path)).replace("_", "-")
    explicit_wine_document = any(word in folded for word in WINE_DOCUMENT_WORDS)
    explicit_wine_path = any(
        word in path
        for word in (
            "wine-list", "winelist", "wine_menu", "wine-menu", "wines", "pricelist",
            "price-list", "carte-des-vins", "carta-vini", "carta-de-vinos", "weinliste",
            "weinkarte", "wijnkaart", "vinkort", "vinlista",
        )
    )
    non_wine_score = sum(min(folded.count(word), 4) for word in NON_WINE_DOCUMENT_WORDS)
    if non_wine_score >= 3 and not explicit_wine_document:
        return [], "PDF was identified as a non-wine document."
    if not products:
        return [], "PDF contained no recognizable Burgundy, Champagne, or Bordeaux wine rows."

    # A generic PDF with one accidental grape or region name is not enough.
    # Real lists either identify themselves or contain several independent rows.
    distinct_rows = {fold_text(product.get("raw_text")) for product in products}
    if not (explicit_wine_document or explicit_wine_path) and len(distinct_rows) < 3:
        return [], "PDF did not contain enough independent wine-list rows."
    return products, ""


def parse_csv_products(body, source_url):
    text = body.decode("utf-8-sig", errors="replace")
    products = []
    for row in csv.reader(io.StringIO(text)):
        product = product_from_text(" ".join(row), source_url)
        if product:
            products.append(product)
    return products


def parse_xlsx_products(body, source_url):
    products = []
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in root]
            for name in archive.namelist():
                if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                    continue
                root = ET.fromstring(archive.read(name))
                for row in root.iter():
                    if not row.tag.endswith("}row"):
                        continue
                    values = []
                    for cell in row:
                        value_node = next((child for child in cell.iter() if child.tag.endswith("}v")), None)
                        if value_node is None or value_node.text is None:
                            continue
                        value = value_node.text
                        if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                            value = shared[int(value)]
                        values.append(value)
                    product = product_from_text(" ".join(values), source_url)
                    if product:
                        products.append(product)
    except (zipfile.BadZipFile, ET.ParseError, OSError):
        pass
    return products


def link_priority(url, label):
    folded = fold_text(f"{url} {label}")
    score = sum(8 for word in WINE_PATH_WORDS if word in folded)
    if urlparse(url).path.lower().endswith((".pdf", ".csv", ".xlsx", ".xls")):
        # A file extension alone says nothing about its contents. Prioritize
        # downloadable files only when their URL or link label is wine-related.
        score += 6 if any(word in folded for word in WINE_PATH_WORDS) else -6
    if any(word in folded for word in ("menu", "download", "shop", "product", "collection")):
        score += 3
    if any(word in folded for word in ("privacy", "terms", "login", "account", "cart", "checkout", "blog", "news")):
        score -= 12
    return score


def html_inventory_signals(url, parser, products):
    """Accept visible-text products only when the page behaves like a catalogue."""
    if not products:
        return False
    parsed = urlparse(url)
    path = fold_text(unquote(parsed.path)).replace("_", "-")
    title = fold_text(" ".join(parser.title + parser.headings))
    page_context = f"{path} {title}"
    context_words = set(re.findall(r"[a-z0-9]+", page_context))
    if any(word in context_words for word in EDITORIAL_PATH_WORDS):
        return False

    segments = {segment for segment in path.split("/") if segment}
    catalogue_path = any(word in segments for word in CATALOG_PATH_WORDS)
    product_path = any(word in segments for word in ("wine", "product"))
    priced_count = sum(product.get("price_value") is not None for product in products)
    page_text = fold_text(" ".join(parser.text[:12000]))
    commerce_text = any(word in page_text for word in COMMERCE_TEXT_WORDS)
    commerce_link = any(
        any(word in fold_text(f"{href} {label}") for word in ("cart", "checkout", "product", "shop"))
        for href, label in parser.links
    )

    if catalogue_path and (priced_count >= 1 or len(products) >= 3):
        return True
    if product_path and priced_count >= 1:
        return True
    return priced_count >= 2 and (commerce_text or commerce_link)


def same_domain(left, right):
    a = (urlparse(left).hostname or "").lower().removeprefix("www.")
    b = (urlparse(right).hostname or "").lower().removeprefix("www.")
    return a == b


def crawl_merchant_inventory(merchant, max_pages=160, max_depth=5, domain_slots=None, robots=None):
    website = merchant["website_url"]
    if not website:
        return {"merchant_id": merchant["id"], "status": "missing_website", "sources": [], "error": "No official website."}
    base = website if website.startswith(("http://", "https://")) else "https://" + website
    sources = []
    products_by_source = {}
    errors = []
    root_response = fetch_url(base, timeout=22, domain_slots=domain_slots, robots=robots)
    if root_response["status"] != 200:
        return {"merchant_id": merchant["id"], "status": "review", "sources": [], "error": root_response.get("error") or f"HTTP {root_response['status']}"}
    root_text = root_response["body"].decode("utf-8", errors="replace")
    root_folded = fold_text(root_text[:100000])
    platform = ""
    if "cdn.shopify.com" in root_text or "shopify.theme" in root_folded:
        platform = "shopify"
        products = shopify_products(base, domain_slots, robots)
        if products:
            source_url = urljoin(base, "/products.json")
            sources.append({"url": source_url, "type": "json", "platform": platform, "status": "found", "confidence": 1.0})
            products_by_source[source_url] = products
    if "woocommerce" in root_folded or "wp-content/plugins/woocommerce" in root_folded:
        platform = platform or "woocommerce"
        products = woo_products(base, domain_slots, robots)
        if products:
            source_url = urljoin(base, "/wp-json/wc/store/v1/products")
            sources.append({"url": source_url, "type": "json", "platform": "woocommerce", "status": "found", "confidence": 1.0})
            products_by_source[source_url] = products

    queue = []
    push_order = 0

    def enqueue(priority, depth, url, prefetched=None):
        nonlocal push_order
        push_order += 1
        heapq.heappush(queue, (-priority, depth, push_order, url, prefetched))

    enqueue(100, 0, root_response["url"], root_response)
    enqueue(18, 1, urljoin(base, "/sitemap.xml"))
    seen = set()
    corksy_catalogs = set()
    while queue and len(seen) < max_pages:
        _negative_priority, depth, _order, url, prefetched = heapq.heappop(queue)
        normalized_url = url.split("#", 1)[0]
        if normalized_url in seen or depth > max_depth:
            continue
        seen.add(normalized_url)
        response = prefetched or fetch_url(
            normalized_url,
            timeout=22,
            domain_slots=domain_slots,
            robots=robots,
        )
        if response["status"] != 200:
            errors.append(response.get("error") or f"HTTP {response['status']} {normalized_url}")
            continue
        content_type = (response["content_type"] or "").lower()
        final_url = response["url"]
        products = []
        source_type = "html"
        source_platform = platform
        is_corksy_source = False
        parser = None
        if "pdf" in content_type or final_url.lower().endswith(".pdf"):
            source_type = "pdf"
            products, parse_error = parse_pdf_products(response["body"], final_url)
            if parse_error:
                errors.append(parse_error)
        elif "csv" in content_type or final_url.lower().endswith(".csv"):
            source_type = "csv"
            products = parse_csv_products(response["body"], final_url)
        elif final_url.lower().endswith(".xlsx") or "spreadsheetml" in content_type:
            source_type = "xlsx"
            products = parse_xlsx_products(response["body"], final_url)
        elif "xml" in content_type or final_url.lower().endswith(".xml"):
            try:
                xml_root = ET.fromstring(response["body"])
                for node in xml_root.iter():
                    if not node.tag.endswith("loc") or not node.text:
                        continue
                    next_url = node.text.strip()
                    if same_domain(base, next_url):
                        enqueue(link_priority(next_url, "sitemap"), min(max_depth, depth + 1), next_url)
            except ET.ParseError:
                errors.append(f"Could not parse sitemap: {final_url}")
        elif "html" in content_type or not content_type:
            html = response["body"].decode("utf-8", errors="replace")
            parser = LinkTextParser()
            try:
                parser.feed(html)
            except Exception:
                parser = None
            if parser:
                corksy_config = corksy_config_from_html(html)
                if not corksy_config and "data-widget-config" in html:
                    expanded = fetch_url(
                        final_url,
                        timeout=22,
                        headers={"Accept": "*/*", "Accept-Language": ""},
                        domain_slots=domain_slots,
                        robots=robots,
                    )
                    if expanded["status"] == 200:
                        expanded_html = expanded["body"].decode("utf-8", errors="replace")
                        corksy_config = corksy_config_from_html(expanded_html)
                if corksy_config:
                    catalog_key = (corksy_config["app_key"], tuple(corksy_config["collection_ids"]))
                    if catalog_key not in corksy_catalogs:
                        corksy_catalogs.add(catalog_key)
                        catalog_products = corksy_products(final_url, html, domain_slots, corksy_config)
                        if catalog_products:
                            products.extend(catalog_products)
                            source_platform = "corksy"
                            is_corksy_source = True
                products.extend(structured_products(parse_json_ld(parser), final_url))
                if link_priority(final_url, "") > 0 or any(term in fold_text(" ".join(parser.text[:3000])) for term in WINE_EVIDENCE):
                    visible_products = []
                    for line in visible_lines(parser):
                        product = product_from_text(line, final_url)
                        if product:
                            visible_products.append(product)
                    if html_inventory_signals(final_url, parser, visible_products):
                        products.extend(visible_products)
        if products:
            deduped = {}
            for product in products:
                deduped[(product["source_key"], product.get("price_value"))] = product
            products = list(deduped.values())
            if is_corksy_source:
                source_type = "json"
            sources.append({"url": final_url, "type": source_type, "platform": source_platform, "status": "found", "confidence": 0.98 if is_corksy_source else 0.95 if source_type != "html" else 0.8})
            products_by_source[final_url] = products
        if parser and depth < max_depth:
            for href, label in parser.links:
                next_url = urljoin(final_url, href).split("#", 1)[0]
                parsed = urlparse(next_url)
                if parsed.scheme not in {"http", "https"} or not same_domain(base, next_url):
                    continue
                if next_url in seen:
                    continue
                priority = link_priority(next_url, label)
                if depth == 0 or priority >= 0:
                    enqueue(priority, depth + 1, next_url)
    unique_sources = {}
    for source in sources:
        unique_sources[source["url"]] = source
    sources = list(unique_sources.values())
    blocked_or_unreadable = any(
        marker in error.lower()
        for error in errors
        for marker in ("robots.txt", "pdf extraction failed", "could not parse sitemap")
    )
    status = "found" if products_by_source else "review" if blocked_or_unreadable else "no_wine_list"
    return {
        "merchant_id": merchant["id"], "status": status, "sources": sources,
        "products": products_by_source, "error": "; ".join(dict.fromkeys(errors))[:2000],
        "pages_checked": len(seen),
    }


def crawl_inventory_batch(merchants, max_pages, max_depth, per_domain, thread_workers):
    """Run one I/O-heavy crawl batch inside a separate Python process."""
    domain_slots = DomainSlots(per_domain)
    robots = RobotsPolicy(domain_slots)
    results = []
    with ThreadPoolExecutor(max_workers=max(1, min(thread_workers, len(merchants)))) as pool:
        futures = {
            pool.submit(
                crawl_merchant_inventory,
                merchant,
                max_pages,
                max_depth,
                domain_slots,
                robots,
            ): merchant
            for merchant in merchants
        }
        for future in as_completed(futures):
            merchant = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "merchant_id": merchant["id"],
                    "status": "review",
                    "sources": [],
                    "error": str(exc),
                }
            results.append((merchant, result))
    return results


def save_inventory_result(con, result):
    merchant_id = result["merchant_id"]
    now = utc_now()
    con.execute(
        "update merchants set inventory_status=?,inventory_error=?,last_inventory_checked_at=? where id=?",
        (result["status"], result.get("error") or "", now, merchant_id),
    )
    # A temporary network/parser failure must not erase the last known-good inventory.
    if result["status"] != "review":
        con.execute("update merchant_products set active=0 where merchant_id=?", (merchant_id,))
        con.execute(
            "update merchant_sources set status='stale' where merchant_id=? and status='found'",
            (merchant_id,),
        )
    seen_source_ids = []
    product_count = 0
    for source in result.get("sources") or []:
        con.execute(
            """
            insert into merchant_sources(
              merchant_id,source_type,source_url,platform,status,parser_status,confidence,
              first_seen_at,last_seen_at,last_checked_at,last_success_at,last_error
            ) values(?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(merchant_id,source_url) do update set
              source_type=excluded.source_type,platform=excluded.platform,status=excluded.status,
              parser_status=excluded.parser_status,confidence=excluded.confidence,last_seen_at=excluded.last_seen_at,
              last_checked_at=excluded.last_checked_at,last_success_at=excluded.last_success_at,last_error=excluded.last_error
            """,
            (
                merchant_id, source["type"], source["url"], source.get("platform") or "",
                source["status"], "parsed", source.get("confidence"), now, now, now, now, "",
            ),
        )
        source_id = con.execute("select id from merchant_sources where merchant_id=? and source_url=?", (merchant_id, source["url"])).fetchone()[0]
        seen_source_ids.append(source_id)
        items = result.get("products", {}).get(source["url"], [])
        for item in items:
            upsert_product(con, merchant_id, source_id, item)
            product_count += 1
        con.execute("update merchant_sources set item_count=? where id=?", (len(items), source_id))
    if result["status"] == "review":
        detail = result.get("error") or "Unknown error"
        existing = con.execute(
            "select id from merchant_reviews where merchant_id=? and reason='inventory_fetch_failed' and status='open' order by id desc limit 1",
            (merchant_id,),
        ).fetchone()
        if existing:
            con.execute(
                "update merchant_reviews set detail=?,created_at=? where id=?",
                (detail, now, existing[0]),
            )
        else:
            con.execute(
                "insert into merchant_reviews(merchant_id,reason,detail) values(?,?,?)",
                (merchant_id, "inventory_fetch_failed", detail),
            )
    else:
        con.execute(
            "update merchant_reviews set status='resolved',resolved_at=? where merchant_id=? and reason='inventory_fetch_failed' and status='open'",
            (now, merchant_id),
        )
    return product_count


def select_inventory_merchants(con, args, stale_before):
    conditions = ["active=1", "website_url is not null", "trim(website_url)!=''"]
    params = []
    if args.merchant_id:
        conditions.append("id=?")
        params.append(args.merchant_id)
    country = str(getattr(args, "country", "") or "").strip()
    if country:
        conditions.append("lower(trim(coalesce(country,'')))=lower(?)")
        params.append(country)
    if args.resume:
        conditions.append("(last_inventory_checked_at is null or last_inventory_checked_at < ?)")
        params.append(stale_before)
    sql = f"select * from merchants where {' and '.join(conditions)} order by coalesce(last_inventory_checked_at,''), id"
    if args.limit:
        sql += " limit ?"
        params.append(args.limit)
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def run_inventory(args):
    ensure_shop_db(args.db)
    con = connect_shop(args.db)
    stale_before = (datetime.now(timezone.utc) - timedelta(days=args.stale_days)).isoformat(timespec="seconds")
    country = str(getattr(args, "country", "") or "").strip()
    merchants = select_inventory_merchants(con, args, stale_before)
    run_id = con.execute(
        "insert into merchant_scan_runs(phase,status,range_start,range_end) values('inventory','running',0,?)",
        (len(merchants),),
    ).lastrowid
    con.commit()
    total = len(merchants)
    checked = found = errors = products = 0
    started = time.monotonic()
    started_at = utc_now()
    process_workers = max(1, min(args.processes, args.workers))
    thread_workers = max(1, (args.workers + process_workers - 1) // process_workers)
    batches = [
        merchants[index:index + thread_workers]
        for index in range(0, len(merchants), thread_workers)
    ]
    try:
        atomic_progress({
            "generatedAt": utc_now(), "startedAt": started_at,
            "status": "running", "phase": "inventory",
            "stageIndex": 4, "stageCount": 4,
            "stageLabel": "Scan websites and save inventories", "stageStatus": "running",
            "stageProcessed": 0, "stageTotal": total,
            "message": "Preparing the saved wine-shop website queue.",
            "runId": run_id, "checked": 0, "total": total, "remaining": total,
            "country": country,
            "found": 0, "products": 0, "errors": 0,
            "workers": args.workers, "processes": process_workers,
            "threadsPerProcess": thread_workers,
            "maxPages": args.max_pages, "maxDepth": args.depth,
        })
        with ProcessPoolExecutor(max_workers=process_workers) as pool:
            futures = {
                pool.submit(
                    crawl_inventory_batch,
                    batch,
                    args.max_pages,
                    args.depth,
                    args.per_domain,
                    thread_workers,
                ): batch
                for batch in batches
            }
            for future in as_completed(futures):
                try:
                    batch_results = future.result()
                except Exception as exc:
                    batch_results = [
                        (
                            merchant,
                            {"merchant_id": merchant["id"], "status": "review", "sources": [], "error": str(exc)},
                        )
                        for merchant in futures[future]
                    ]
                for merchant, result in batch_results:
                    checked += 1
                    if result["status"] == "found":
                        found += 1
                    if result["status"] == "review":
                        errors += 1
                    products += save_inventory_result(con, result)
                    if checked % 5 == 0 or checked == total:
                        con.commit()
                        elapsed = max(0.001, time.monotonic() - started)
                        atomic_progress({
                            "generatedAt": utc_now(), "startedAt": started_at,
                            "status": "running", "phase": "inventory",
                            "stageIndex": 4, "stageCount": 4,
                            "stageLabel": "Scan websites and save inventories", "stageStatus": "running",
                            "stageProcessed": checked, "stageTotal": total,
                            "message": "Scanning official websites and saving verified catalogues.",
                            "runId": run_id, "checked": checked, "total": total, "remaining": total - checked,
                            "country": country,
                            "found": found, "products": products, "errors": errors, "currentMerchant": merchant["name"],
                            "elapsedSeconds": int(elapsed),
                            "estimatedRemainingSeconds": int((total - checked) / max(0.01, checked / elapsed)),
                            "workers": args.workers, "processes": process_workers,
                            "threadsPerProcess": thread_workers,
                            "maxPages": args.max_pages, "maxDepth": args.depth,
                        })
        con.execute("update merchant_scan_runs set status='done',finished_at=?,checked=?,found=?,errors=? where id=?", (utc_now(), checked, found, errors, run_id))
        con.commit()
        atomic_progress({
            "generatedAt": utc_now(), "startedAt": started_at,
            "status": "done", "phase": "inventory_complete",
            "stageIndex": 4, "stageCount": 4,
            "stageLabel": "Scan websites and save inventories", "stageStatus": "complete",
            "stageProcessed": checked, "stageTotal": total,
            "message": "Wine-shop inventory scan completed.",
            "runId": run_id, "checked": checked, "total": total,
            "country": country,
            "remaining": 0, "found": found, "products": products, "errors": errors,
        })
    finally:
        con.close()


def build_parser():
    parser = argparse.ArgumentParser(description="Collect public wine merchant profiles and official inventory sources.")
    parser.add_argument("--db", default=str(SHOP_DB_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    merchant = sub.add_parser("merchant-scan", help="Scan the public Wine-Searcher merchant ID range once.")
    merchant.add_argument("--start", type=int, default=2)
    merchant.add_argument("--end", type=int, default=239995)
    merchant.add_argument("--workers", type=int, default=24)
    merchant.add_argument("--rps", type=float, default=4.0)
    merchant.add_argument("--max-rps", type=float, default=8.0)
    merchant.add_argument("--batch-size", type=int, default=250)
    merchant.add_argument("--block-threshold", type=int, default=20)
    merchant.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)

    inventory = sub.add_parser("inventory", help="Collect official merchant websites and price lists.")
    inventory.add_argument("--workers", type=int, default=96)
    inventory.add_argument("--processes", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    inventory.add_argument("--per-domain", type=int, default=2)
    inventory.add_argument("--max-pages", type=int, default=160)
    inventory.add_argument("--depth", type=int, default=5)
    inventory.add_argument("--stale-days", type=int, default=14)
    inventory.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    inventory.add_argument("--limit", type=int, default=0)
    inventory.add_argument("--merchant-id", type=int, default=0)
    inventory.add_argument("--country", default="", help="Only scan merchants matching this stored country code or name.")
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == "merchant-scan":
        run_merchant_scan(args)
    elif args.command == "inventory":
        run_inventory(args)


if __name__ == "__main__":
    main()
