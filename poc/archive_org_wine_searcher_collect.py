#!/usr/bin/env python3
"""Collect a 1,000-merchant Wine-Searcher PoC from public Wayback snapshots.

This does not access Wine-Searcher directly and does not attempt to bypass its
access controls. It uses public CDX metadata and archived public merchant pages.
Every row records the capture timestamp so stale data is explicit.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests
from bs4 import BeautifulSoup

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
WAYBACK_BASE = "https://web.archive.org/web/{timestamp}id_/{original}"
KNOWN_TYPES = [
    "Retail chain", "Auction house", "Wine Club", "Wholesaler", "Distributor",
    "Restaurant", "Retailer", "Producer", "Winery", "Brewery", "Distillery",
    "Broker", "Importer", "En Primeur",
]
SOCIAL_HOSTS = {
    "google.com", "www.google.com", "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com", "linkedin.com", "www.linkedin.com",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
}


@dataclass
class Capture:
    merchant_id: int
    timestamp: str
    original: str
    statuscode: str
    mimetype: str
    digest: str


@dataclass
class Merchant:
    requested_id: int
    source: str
    capture_timestamp: str
    capture_datetime_utc: str
    original_url: str
    archive_url: str
    result_status: str
    archive_status_code: int | None = None
    final_archive_url: str = ""
    slug: str = ""
    name: str = ""
    merchant_types: str = ""
    description: str = ""
    website_url: str = ""
    website_domain: str = ""
    item_count: int | None = None
    price_list_collected: str = ""
    price_list_update_frequency: str = ""
    business_listed_since: str = ""
    country_region: str = ""
    address: str = ""
    phone: str = ""
    wine_signal: int = 0
    wine_signal_score: int = 0
    elapsed_ms: int = 0
    response_bytes: int = 0
    error: str = ""


class Limiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, min_interval)
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.min_interval
        if delay:
            time.sleep(delay)
        time.sleep(random.uniform(0.02, 0.09))


local = threading.local()


def get_session() -> requests.Session:
    session = getattr(local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "whereiskelley-wayback-merchant-poc/0.1 (public archive research)",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        local.session = session
    return session


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def first_match(pattern: str, text: str, flags: int = re.I) -> str:
    match = re.search(pattern, text, flags)
    return clean(match.group(1)) if match else ""


def capture_datetime(timestamp: str) -> str:
    try:
        dt = datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return ""


def extract_merchant_id(url: str) -> int | None:
    match = re.search(r"/merchant/0*(\d+)(?:[-/?#]|$)", url, re.I)
    if not match:
        return None
    value = int(match.group(1))
    return value if value > 0 else None


def is_clean_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return not parsed.query and bool(re.fullmatch(r"/merchant/0*\d+(?:-[^/?#]+)?", path, re.I))


def cdx_records(limit: int, from_year: int, to_year: int) -> list[dict[str, str]]:
    params = [
        ("url", "www.wine-searcher.com/merchant/"),
        ("matchType", "prefix"),
        ("output", "json"),
        ("fl", "timestamp,original,statuscode,mimetype,digest"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("from", str(from_year)),
        ("to", str(to_year)),
        ("collapse", "urlkey"),
        ("limit", str(limit)),
    ]
    url = CDX_ENDPOINT + "?" + urlencode(params)
    session = get_session()
    response = session.get(url, timeout=180)
    print(f"CDX status={response.status_code} bytes={len(response.content)}", flush=True)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return []
    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:]]


def choose_captures(records: list[dict[str, str]], target_count: int) -> list[Capture]:
    selected: dict[int, Capture] = {}
    for record in records:
        original = record.get("original", "")
        merchant_id = extract_merchant_id(original)
        if merchant_id is None:
            continue
        if not is_clean_profile_url(original):
            continue
        candidate = Capture(
            merchant_id=merchant_id,
            timestamp=record.get("timestamp", ""),
            original=original,
            statuscode=record.get("statuscode", ""),
            mimetype=record.get("mimetype", ""),
            digest=record.get("digest", ""),
        )
        current = selected.get(merchant_id)
        # Prefer newer capture, then a slug-bearing URL over numeric-only URL.
        if current is None:
            selected[merchant_id] = candidate
        else:
            candidate_has_slug = bool(re.search(r"/merchant/0*\d+-", candidate.original))
            current_has_slug = bool(re.search(r"/merchant/0*\d+-", current.original))
            if candidate.timestamp > current.timestamp or (
                candidate.timestamp == current.timestamp and candidate_has_slug and not current_has_slug
            ):
                selected[merchant_id] = candidate
    captures = sorted(selected.values(), key=lambda item: (item.merchant_id, item.timestamp))
    return captures[:target_count]


def unrewrite_wayback_url(href: str) -> str:
    href = clean(href)
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    # Typical Wayback rewrite: /web/<timestamp>id_/https://example.com/path
    match = re.search(r"/web/\d+(?:[a-z_]+)?/(https?://.+)$", href, re.I)
    if match:
        return unquote(match.group(1))
    match = re.search(r"https?://web\.archive\.org/web/\d+(?:[a-z_]+)?/(https?://.+)$", href, re.I)
    if match:
        return unquote(match.group(1))
    return href


def find_external_website(soup: BeautifulSoup) -> tuple[str, str]:
    candidates: list[tuple[int, str, str]] = []
    for anchor in soup.find_all("a", href=True):
        raw = anchor.get("href", "")
        href = unrewrite_wayback_url(raw)
        if not href.startswith(("http://", "https://")):
            continue
        try:
            parsed = urlparse(href)
        except ValueError:
            continue
        host = parsed.netloc.lower().split(":")[0]
        if not host:
            continue
        if host == "web.archive.org" or host == "wine-searcher.com" or host.endswith(".wine-searcher.com"):
            continue
        if host in SOCIAL_HOSTS:
            continue
        label = clean(anchor.get_text(" ", strip=True)).lower()
        score = 0
        if "see website" in label:
            score += 100
        elif "website" in label or "visit" in label:
            score += 70
        if "merchant" in label or "shop" in label:
            score += 20
        if parsed.path in ("", "/"):
            score += 5
        candidates.append((score, href, host))
    if not candidates:
        return "", ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, href, host = candidates[0]
    return href, host


def section_text(soup: BeautifulSoup, heading_text: str, limit: int = 1000) -> str:
    heading = None
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        if heading_text.lower() in clean(tag.get_text(" ", strip=True)).lower():
            heading = tag
            break
    if heading is None:
        return ""
    pieces: list[str] = []
    for node in heading.next_siblings:
        name = getattr(node, "name", None)
        if name and re.match(r"^h[1-6]$", name):
            break
        text = clean(node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node))
        if text:
            pieces.append(text)
        if len(" ".join(pieces)) >= limit:
            break
    return clean(" ".join(pieces))[:limit]


def parse_snapshot(capture: Capture, response: requests.Response, elapsed_ms: int) -> Merchant:
    archive_url = WAYBACK_BASE.format(timestamp=capture.timestamp, original=capture.original)
    result = Merchant(
        requested_id=capture.merchant_id,
        source="wayback",
        capture_timestamp=capture.timestamp,
        capture_datetime_utc=capture_datetime(capture.timestamp),
        original_url=capture.original,
        archive_url=archive_url,
        result_status="unknown",
        archive_status_code=response.status_code,
        final_archive_url=response.url,
        elapsed_ms=elapsed_ms,
        response_bytes=len(response.content),
    )
    path_match = re.search(r"/merchant/0*\d+(?:-([^/?#]+))?", capture.original)
    result.slug = path_match.group(1) if path_match and path_match.group(1) else ""

    if response.status_code == 404:
        result.result_status = "archive_not_found"
        return result
    if response.status_code == 429:
        result.result_status = "archive_rate_limited"
        return result
    if response.status_code in (401, 403):
        result.result_status = "archive_blocked"
        return result
    if response.status_code >= 500:
        result.result_status = "archive_server_error"
        return result
    if response.status_code >= 400:
        result.result_status = "archive_http_error"
        return result

    html = response.text
    lower_head = html[:50000].lower()
    if "this url has been excluded from the wayback machine" in lower_head:
        result.result_status = "archive_excluded"
        return result
    if "robots.txt" in lower_head and "blocked" in lower_head:
        result.result_status = "archive_robots_blocked"
        return result

    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    result.name = clean(h1.get_text(" ", strip=True)) if h1 else ""
    page_text = clean(soup.get_text(" ", strip=True))
    markers = sum(
        marker.lower() in page_text.lower()
        for marker in ("Contact details", "Delivery & Services", "Business listed since", "Price list")
    )
    if not result.name or markers == 0:
        result.result_status = "invalid_snapshot"
        return result

    result.result_status = "merchant"
    top_text = clean((h1.parent.get_text(" ", strip=True) if h1 and h1.parent else "") + " " + page_text[:4000])
    hits = []
    for merchant_type in KNOWN_TYPES:
        if re.search(rf"\b{re.escape(merchant_type)}\b", top_text, re.I):
            hits.append(merchant_type)
    result.merchant_types = " · ".join(dict.fromkeys(hits))

    if h1:
        candidates: list[str] = []
        for sibling in h1.find_all_next(limit=10):
            if sibling is h1:
                continue
            if getattr(sibling, "name", "") in {"p", "div", "span"}:
                value = clean(sibling.get_text(" ", strip=True))
                if 3 <= len(value) <= 500 and value != result.merchant_types:
                    if not any(token in value.lower() for token in ("sign in", "menu", "share this page")):
                        candidates.append(value)
            if candidates:
                break
        result.description = candidates[0] if candidates else ""

    result.website_url, result.website_domain = find_external_website(soup)
    item_text = first_match(r"([0-9][0-9,]*)\s*(?:items|products)\b", page_text)
    if item_text:
        try:
            result.item_count = int(item_text.replace(",", ""))
        except ValueError:
            pass
    result.price_list_collected = first_match(
        r"Price list collected\s*:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", page_text
    )
    result.price_list_update_frequency = first_match(r"Price list updated\s+([^\.]{2,80})\.", page_text)
    result.business_listed_since = first_match(
        r"Business listed since\s+([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", page_text
    )

    contact = section_text(soup, "Contact details", 1200)
    result.phone = first_match(r"(\+?[0-9][0-9 ()\-]{6,}[0-9])", contact)
    address = re.sub(r"\bOpen\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday).*", "", contact, flags=re.I)
    address = re.sub(r"\+?[0-9][0-9 ()\-]{6,}[0-9].*", "", address)
    address = clean(address)
    result.address = address[:400]
    region = re.match(r"([A-Za-z .'-]+(?:\([^)]+\))?)", address)
    result.country_region = clean(region.group(1))[:150] if region else ""

    score = 0
    lower = page_text.lower()
    if "wines ship" in lower:
        score += 3
    if "wine merchant" in lower:
        score += 3
    if re.search(r"wine club|winery", result.merchant_types, re.I):
        score += 2
    if result.website_url and re.search(r"wine|vin|cellar", result.website_url, re.I):
        score += 1
    if re.search(r"\bwine\b", f"{result.name} {result.description}", re.I):
        score += 2
    result.wine_signal_score = score
    result.wine_signal = int(score >= 2)
    return result


def fetch_capture(capture: Capture, limiter: Limiter, timeout: float, retries: int) -> Merchant:
    url = WAYBACK_BASE.format(timestamp=capture.timestamp, original=capture.original)
    session = get_session()
    last_error = ""
    for attempt in range(retries + 1):
        limiter.wait()
        started = time.perf_counter()
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            result = parse_snapshot(capture, response, elapsed_ms)
            if result.result_status in {"archive_rate_limited", "archive_server_error"} and attempt < retries:
                time.sleep(min(30, (2 ** attempt) * 2 + random.uniform(0.2, 1.0)))
                continue
            return result
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"[:500]
            if attempt < retries:
                time.sleep((2 ** attempt) + random.uniform(0.2, 0.8))
                continue
            return Merchant(
                requested_id=capture.merchant_id,
                source="wayback",
                capture_timestamp=capture.timestamp,
                capture_datetime_utc=capture_datetime(capture.timestamp),
                original_url=capture.original,
                archive_url=url,
                result_status="request_error",
                error=last_error,
            )
    raise AssertionError("unreachable")


def collect(captures: list[Capture], workers: int, interval: float, timeout: float, retries: int) -> list[Merchant]:
    limiter = Limiter(interval)
    results: list[Merchant] = []
    total = len(captures)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(fetch_capture, capture, limiter, timeout, retries): capture
            for capture in captures
        }
        for index, future in enumerate(as_completed(futures), 1):
            capture = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = Merchant(
                    requested_id=capture.merchant_id,
                    source="wayback",
                    capture_timestamp=capture.timestamp,
                    capture_datetime_utc=capture_datetime(capture.timestamp),
                    original_url=capture.original,
                    archive_url=WAYBACK_BASE.format(timestamp=capture.timestamp, original=capture.original),
                    result_status="worker_error",
                    error=f"{type(exc).__name__}: {exc}"[:500],
                )
            results.append(result)
            if index <= 10 or index % 25 == 0 or index == total:
                counts = Counter(item.result_status for item in results)
                print(
                    f"progress={index}/{total} merchant={counts['merchant']} "
                    f"invalid={counts['invalid_snapshot']} not_found={counts['archive_not_found']} "
                    f"blocked={counts['archive_blocked'] + counts['archive_robots_blocked'] + counts['archive_excluded']} "
                    f"rate_limited={counts['archive_rate_limited']} request_error={counts['request_error']}",
                    flush=True,
                )
    return sorted(results, key=lambda item: item.requested_id)


def pilot_ok(results: list[Merchant]) -> tuple[bool, str]:
    if not results:
        return False, "pilot returned no results"
    counts = Counter(item.result_status for item in results)
    usable = counts["merchant"]
    blocked = counts["archive_blocked"] + counts["archive_robots_blocked"] + counts["archive_excluded"]
    unstable = counts["archive_rate_limited"] + counts["archive_server_error"] + counts["request_error"]
    if blocked / len(results) >= 0.50:
        return False, f"archive blocked/excluded ratio too high: {blocked}/{len(results)}"
    if unstable / len(results) >= 0.40:
        return False, f"archive instability ratio too high: {unstable}/{len(results)}"
    if usable < max(3, len(results) // 5):
        return False, f"too few parseable merchants: {usable}/{len(results)}"
    return True, "pilot passed"


def write_outputs(outdir: Path, captures: list[Capture], results: list[Merchant], summary: dict[str, Any]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    capture_columns = [field.name for field in fields(Capture)]
    with (outdir / "capture_index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=capture_columns)
        writer.writeheader()
        for capture in captures:
            writer.writerow(asdict(capture))

    columns = [field.name for field in fields(Merchant)]
    with (outdir / "wine_searcher_merchants_wayback.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))

    db_path = outdir / "wine_searcher_merchants_wayback.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE captures (
                merchant_id INTEGER PRIMARY KEY,
                timestamp TEXT,
                original TEXT,
                statuscode TEXT,
                mimetype TEXT,
                digest TEXT
            );
            CREATE TABLE merchants (
                requested_id INTEGER PRIMARY KEY,
                source TEXT,
                capture_timestamp TEXT,
                capture_datetime_utc TEXT,
                original_url TEXT,
                archive_url TEXT,
                result_status TEXT,
                archive_status_code INTEGER,
                final_archive_url TEXT,
                slug TEXT,
                name TEXT,
                merchant_types TEXT,
                description TEXT,
                website_url TEXT,
                website_domain TEXT,
                item_count INTEGER,
                price_list_collected TEXT,
                price_list_update_frequency TEXT,
                business_listed_since TEXT,
                country_region TEXT,
                address TEXT,
                phone TEXT,
                wine_signal INTEGER,
                wine_signal_score INTEGER,
                elapsed_ms INTEGER,
                response_bytes INTEGER,
                error TEXT
            );
            CREATE INDEX idx_merchants_status ON merchants(result_status);
            CREATE INDEX idx_merchants_domain ON merchants(website_domain);
            CREATE INDEX idx_merchants_wine ON merchants(wine_signal);
            """
        )
        conn.executemany(
            "INSERT INTO captures VALUES (?, ?, ?, ?, ?, ?)",
            [[getattr(c, column) for column in capture_columns] for c in captures],
        )
        placeholders = ",".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO merchants ({','.join(columns)}) VALUES ({placeholders})",
            [[getattr(row, column) for column in columns] for row in results],
        )
        conn.commit()
    finally:
        conn.close()

    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (outdir / "errors.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            if result.result_status != "merchant":
                handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--cdx-limit", type=int, default=15000)
    parser.add_argument("--from-year", type=int, default=2024)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--pilot", type=int, default=25)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--interval", type=float, default=0.22)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/wine-searcher-wayback-poc"))
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    records = cdx_records(args.cdx_limit, args.from_year, args.to_year)
    captures = choose_captures(records, args.count)
    print(json.dumps({
        "cdx_records": len(records),
        "selected_unique_captures": len(captures),
        "requested_count": args.count,
        "first_ids": [c.merchant_id for c in captures[:10]],
        "last_ids": [c.merchant_id for c in captures[-10:]],
    }, ensure_ascii=False), flush=True)

    pilot_captures = captures[: min(args.pilot, len(captures))]
    results = collect(pilot_captures, args.workers, args.interval, args.timeout, args.retries)
    ok, reason = pilot_ok(results)
    print(f"pilot_ok={ok} reason={reason}", flush=True)

    if ok and len(pilot_captures) < len(captures):
        results.extend(
            collect(captures[len(pilot_captures):], args.workers, args.interval, args.timeout, args.retries)
        )
        results.sort(key=lambda item: item.requested_id)

    finished = datetime.now(timezone.utc)
    counts = Counter(item.result_status for item in results)
    merchants = [item for item in results if item.result_status == "merchant"]
    latencies = [item.elapsed_ms for item in results if item.elapsed_ms > 0]
    capture_years = Counter(item.capture_timestamp[:4] for item in results if item.capture_timestamp)
    summary = {
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "source": "Internet Archive Wayback CDX and archived public pages",
        "requested_count": args.count,
        "cdx_records_received": len(records),
        "unique_captures_selected": len(captures),
        "attempted_count": len(results),
        "pilot_ok": ok,
        "pilot_reason": reason,
        "result_status_counts": dict(sorted(counts.items())),
        "merchant_count": len(merchants),
        "merchant_yield_percent": round(len(merchants) / len(results) * 100, 2) if results else 0,
        "merchant_with_external_website_count": sum(bool(item.website_url) for item in merchants),
        "merchant_with_external_website_percent": round(
            sum(bool(item.website_url) for item in merchants) / len(merchants) * 100, 2
        ) if merchants else 0,
        "merchant_with_item_count_count": sum(item.item_count is not None for item in merchants),
        "wine_signal_count": sum(item.wine_signal for item in merchants),
        "capture_year_counts": dict(sorted(capture_years.items())),
        "mean_elapsed_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "median_elapsed_ms": round(statistics.median(latencies), 2) if latencies else None,
        "sample_merchants": [
            {
                "merchant_id": item.requested_id,
                "capture_timestamp": item.capture_timestamp,
                "name": item.name,
                "merchant_types": item.merchant_types,
                "website_url": item.website_url,
                "item_count": item.item_count,
                "country_region": item.country_region,
            }
            for item in merchants[:20]
        ],
        "limitations": [
            "Data reflects archived capture time, not guaranteed current state.",
            "Login/PRO-only price-list rows are not collected.",
            "External merchant websites are recorded but not crawled in this PoC.",
        ],
    }
    write_outputs(args.output_dir, captures, results, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
