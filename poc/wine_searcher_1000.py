#!/usr/bin/env python3
"""One-time Wine-Searcher public merchant page collection PoC.

The collector intentionally uses only public merchant profile pages. It does not
log in, solve CAPTCHAs, or bypass access controls. It applies a global request
rate, retries transient failures, and stops early when a pilot batch indicates
blocking or severe instability.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.wine-searcher.com/merchant/{merchant_id}"
WS_HOSTS = {"wine-searcher.com", "www.wine-searcher.com"}
EXCLUDED_EXTERNAL_HOSTS = {
    "google.com",
    "www.google.com",
    "maps.google.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "linkedin.com",
    "www.linkedin.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
}
MERCHANT_TYPES = [
    "Retail chain",
    "Auction house",
    "Wine Club",
    "Wholesaler",
    "Distributor",
    "Restaurant",
    "Retailer",
    "Producer",
    "Winery",
    "Brewery",
    "Distillery",
    "Broker",
    "Importer",
    "En Primeur",
]
BLOCK_PATTERNS = [
    "access denied",
    "just a moment",
    "captcha",
    "pardon our interruption",
    "request unsuccessful",
    "temporarily blocked",
    "verify you are human",
]


@dataclass
class MerchantResult:
    requested_id: int
    requested_url: str
    result_status: str
    status_code: int | None = None
    final_url: str = ""
    final_id: int | None = None
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
    response_bytes: int = 0
    elapsed_ms: int = 0
    content_sha256: str = ""
    error: str = ""


class GlobalRateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, min_interval)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.min_interval
        if sleep_for:
            time.sleep(sleep_for)
        time.sleep(random.uniform(0.02, 0.10))


_thread_local = threading.local()


def session_for_thread() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        _thread_local.session = session
    return session


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def first_match(pattern: str, text: str, flags: int = re.I) -> str:
    match = re.search(pattern, text, flags)
    return clean_text(match.group(1)) if match else ""


def parse_final_identity(url: str) -> tuple[int | None, str]:
    path = urlparse(url).path.rstrip("/")
    match = re.search(r"/merchant/(\d+)(?:-([^/?#]+))?$", path)
    if not match:
        return None, ""
    return int(match.group(1)), match.group(2) or ""


def find_external_website(soup: BeautifulSoup) -> tuple[str, str]:
    candidates: list[tuple[int, str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href.startswith(("http://", "https://")):
            continue
        parsed = urlparse(href)
        host = parsed.netloc.lower().split(":")[0]
        if host in WS_HOSTS or host.endswith(".wine-searcher.com"):
            continue
        if host in EXCLUDED_EXTERNAL_HOSTS or href.startswith(("mailto:", "tel:")):
            continue
        label = clean_text(anchor.get_text(" ", strip=True)).lower()
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


def section_text_after_heading(soup: BeautifulSoup, heading_text: str, limit: int = 700) -> str:
    heading = None
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        if heading_text.lower() in clean_text(tag.get_text(" ", strip=True)).lower():
            heading = tag
            break
    if heading is None:
        return ""
    pieces: list[str] = []
    for node in heading.next_siblings:
        name = getattr(node, "name", None)
        if name and re.match(r"^h[1-6]$", name):
            break
        text = clean_text(node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node))
        if text:
            pieces.append(text)
        if sum(len(x) for x in pieces) >= limit:
            break
    return clean_text(" ".join(pieces))[:limit]


def parse_merchant_page(merchant_id: int, response: requests.Response, elapsed_ms: int) -> MerchantResult:
    requested_url = BASE_URL.format(merchant_id=merchant_id)
    body = response.content or b""
    text_lower = response.text[:30000].lower() if body else ""
    result = MerchantResult(
        requested_id=merchant_id,
        requested_url=requested_url,
        result_status="unknown",
        status_code=response.status_code,
        final_url=response.url,
        response_bytes=len(body),
        elapsed_ms=elapsed_ms,
        content_sha256=hashlib.sha256(body).hexdigest() if body else "",
    )
    result.final_id, result.slug = parse_final_identity(response.url)

    if response.status_code == 404:
        result.result_status = "not_found"
        return result
    if response.status_code == 410:
        result.result_status = "gone"
        return result
    if response.status_code == 429:
        result.result_status = "rate_limited"
        return result
    if response.status_code in (401, 403):
        result.result_status = "blocked"
        return result
    if response.status_code >= 500:
        result.result_status = "server_error"
        return result
    if response.status_code >= 400:
        result.result_status = "http_error"
        return result
    if any(pattern in text_lower for pattern in BLOCK_PATTERNS):
        result.result_status = "blocked_page"
        return result

    soup = BeautifulSoup(response.text, "html.parser")
    h1 = soup.find("h1")
    name = clean_text(h1.get_text(" ", strip=True)) if h1 else ""
    page_text = clean_text(soup.get_text(" ", strip=True))

    merchant_markers = sum(
        marker.lower() in page_text.lower()
        for marker in ("Contact details", "Delivery & Services", "Business listed since", "Price list")
    )
    final_is_merchant = result.final_id is not None and "/merchant/" in urlparse(response.url).path
    if not name or not final_is_merchant or merchant_markers == 0:
        result.result_status = "invalid_page"
        result.name = name
        return result

    result.result_status = "merchant"
    result.name = name

    type_hits: list[str] = []
    lead_text = ""
    if h1:
        parent = h1.parent
        lead_text = clean_text(parent.get_text(" ", strip=True))[:700] if parent else ""
    search_text = f"{lead_text} {page_text[:2500]}"
    for merchant_type in MERCHANT_TYPES:
        if re.search(rf"\b{re.escape(merchant_type)}\b", search_text, re.I):
            type_hits.append(merchant_type)
    result.merchant_types = " · ".join(dict.fromkeys(type_hits))

    if h1:
        descriptions: list[str] = []
        for sibling in h1.find_all_next(limit=8):
            if sibling is h1:
                continue
            if getattr(sibling, "name", "") in {"p", "div", "span"}:
                candidate = clean_text(sibling.get_text(" ", strip=True))
                if 3 <= len(candidate) <= 300 and candidate != result.merchant_types:
                    if not any(x in candidate.lower() for x in ("sign in", "menu", "share this page")):
                        descriptions.append(candidate)
            if descriptions:
                break
        result.description = descriptions[0] if descriptions else ""

    result.website_url, result.website_domain = find_external_website(soup)

    item_value = first_match(r"([0-9][0-9,]*)\s*(?:items|products)\b", page_text)
    if item_value:
        try:
            result.item_count = int(item_value.replace(",", ""))
        except ValueError:
            pass

    result.price_list_collected = first_match(
        r"Price list collected\s*:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", page_text
    )
    result.price_list_update_frequency = first_match(
        r"Price list updated\s+([^\.]{2,80})\.", page_text
    )
    result.business_listed_since = first_match(
        r"Business listed since\s+([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", page_text
    )

    contact_text = section_text_after_heading(soup, "Contact details", limit=800)
    result.phone = first_match(r"(\+?[0-9][0-9 ()\-]{6,}[0-9])", contact_text)
    address_candidate = contact_text
    address_candidate = re.sub(r"\bOpen\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday).*", "", address_candidate, flags=re.I)
    address_candidate = re.sub(r"\+?[0-9][0-9 ()\-]{6,}[0-9].*", "", address_candidate)
    address_candidate = clean_text(address_candidate)
    if address_candidate:
        result.address = address_candidate[:300]
        country_match = re.match(r"([A-Za-z .'-]+(?:\([^)]+\))?)", address_candidate)
        if country_match:
            result.country_region = clean_text(country_match.group(1))[:120]

    wine_score = 0
    lower = page_text.lower()
    if "wines ship" in lower:
        wine_score += 3
    if "wine merchant" in lower:
        wine_score += 3
    if "wine club" in lower or "winery" in result.merchant_types.lower():
        wine_score += 2
    if result.website_url and any(token in result.website_url.lower() for token in ("wine", "vin", "cellar")):
        wine_score += 1
    if re.search(r"\bwine\b", f"{result.name} {result.description}", re.I):
        wine_score += 2
    result.wine_signal_score = wine_score
    result.wine_signal = int(wine_score >= 2)
    return result


def fetch_one(
    merchant_id: int,
    limiter: GlobalRateLimiter,
    timeout: float,
    retries: int,
) -> MerchantResult:
    requested_url = BASE_URL.format(merchant_id=merchant_id)
    session = session_for_thread()
    last_error = ""
    for attempt in range(retries + 1):
        limiter.wait()
        started = time.perf_counter()
        try:
            response = session.get(requested_url, timeout=timeout, allow_redirects=True)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            parsed = parse_merchant_page(merchant_id, response, elapsed_ms)
            if parsed.result_status in {"rate_limited", "server_error"} and attempt < retries:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else (2 ** attempt) * 2.0
                except ValueError:
                    delay = (2 ** attempt) * 2.0
                time.sleep(min(30.0, delay + random.uniform(0.2, 1.0)))
                continue
            return parsed
        except requests.RequestException as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            last_error = f"{type(exc).__name__}: {exc}"[:500]
            if attempt < retries:
                time.sleep((2 ** attempt) + random.uniform(0.2, 0.8))
                continue
            return MerchantResult(
                requested_id=merchant_id,
                requested_url=requested_url,
                result_status="request_error",
                elapsed_ms=elapsed_ms,
                error=last_error,
            )
    return MerchantResult(
        requested_id=merchant_id,
        requested_url=requested_url,
        result_status="request_error",
        error=last_error or "unknown request error",
    )


def collect_ids(
    merchant_ids: list[int],
    workers: int,
    min_interval: float,
    timeout: float,
    retries: int,
) -> list[MerchantResult]:
    limiter = GlobalRateLimiter(min_interval)
    results: list[MerchantResult] = []
    total = len(merchant_ids)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(fetch_one, merchant_id, limiter, timeout, retries): merchant_id
            for merchant_id in merchant_ids
        }
        for index, future in enumerate(as_completed(futures), start=1):
            merchant_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # defensive: preserve the batch
                result = MerchantResult(
                    requested_id=merchant_id,
                    requested_url=BASE_URL.format(merchant_id=merchant_id),
                    result_status="worker_error",
                    error=f"{type(exc).__name__}: {exc}"[:500],
                )
            results.append(result)
            if index <= 10 or index % 25 == 0 or index == total:
                counts = Counter(item.result_status for item in results)
                print(
                    f"progress={index}/{total} merchants={counts.get('merchant', 0)} "
                    f"blocked={counts.get('blocked', 0) + counts.get('blocked_page', 0)} "
                    f"rate_limited={counts.get('rate_limited', 0)} errors="
                    f"{sum(v for k, v in counts.items() if k.endswith('error'))}",
                    flush=True,
                )
    return sorted(results, key=lambda item: item.requested_id)


def pilot_is_safe(results: list[MerchantResult]) -> tuple[bool, str]:
    if not results:
        return False, "pilot produced no results"
    counts = Counter(item.result_status for item in results)
    total = len(results)
    blocked = counts.get("blocked", 0) + counts.get("blocked_page", 0)
    rate_limited = counts.get("rate_limited", 0)
    server_errors = counts.get("server_error", 0)
    request_errors = counts.get("request_error", 0)
    if blocked > 0:
        return False, f"pilot detected blocking ({blocked}/{total})"
    if rate_limited / total >= 0.10:
        return False, f"pilot rate-limit ratio too high ({rate_limited}/{total})"
    if (server_errors + request_errors) / total >= 0.40:
        return False, f"pilot instability too high ({server_errors + request_errors}/{total})"
    return True, "pilot passed"


def write_csv(path: Path, results: list[MerchantResult]) -> None:
    columns = [field.name for field in fields(MerchantResult)]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in results:
            writer.writerow(asdict(item))


def write_sqlite(path: Path, results: list[MerchantResult]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE merchants (
                requested_id INTEGER PRIMARY KEY,
                requested_url TEXT NOT NULL,
                result_status TEXT NOT NULL,
                status_code INTEGER,
                final_url TEXT,
                final_id INTEGER,
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
                wine_signal INTEGER NOT NULL DEFAULT 0,
                wine_signal_score INTEGER NOT NULL DEFAULT 0,
                response_bytes INTEGER NOT NULL DEFAULT 0,
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                content_sha256 TEXT,
                error TEXT
            );
            CREATE INDEX idx_merchants_status ON merchants(result_status);
            CREATE INDEX idx_merchants_website_domain ON merchants(website_domain);
            CREATE INDEX idx_merchants_wine_signal ON merchants(wine_signal);
            CREATE UNIQUE INDEX idx_merchants_final_id ON merchants(final_id) WHERE final_id IS NOT NULL;
            """
        )
        columns = [field.name for field in fields(MerchantResult)]
        placeholders = ",".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO merchants ({','.join(columns)}) VALUES ({placeholders})",
            [[getattr(item, column) for column in columns] for item in results],
        )
        conn.commit()
    finally:
        conn.close()


def make_summary(
    results: list[MerchantResult],
    start_id: int,
    requested_count: int,
    pilot_count: int,
    pilot_ok: bool,
    pilot_reason: str,
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, Any]:
    counts = Counter(item.result_status for item in results)
    status_codes = Counter(str(item.status_code) for item in results if item.status_code is not None)
    merchants = [item for item in results if item.result_status == "merchant"]
    latencies = [item.elapsed_ms for item in results if item.elapsed_ms > 0]
    unique_final_ids = {item.final_id for item in merchants if item.final_id is not None}
    duplicate_final_ids = max(0, len(merchants) - len(unique_final_ids))
    return {
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "requested_start_id": start_id,
        "requested_count": requested_count,
        "attempted_count": len(results),
        "pilot_count": pilot_count,
        "pilot_ok": pilot_ok,
        "pilot_reason": pilot_reason,
        "result_status_counts": dict(sorted(counts.items())),
        "http_status_counts": dict(sorted(status_codes.items())),
        "merchant_count": len(merchants),
        "merchant_yield_percent": round((len(merchants) / len(results) * 100), 2) if results else 0.0,
        "unique_final_merchant_ids": len(unique_final_ids),
        "duplicate_final_id_count": duplicate_final_ids,
        "merchant_with_external_website_count": sum(bool(item.website_url) for item in merchants),
        "merchant_with_external_website_percent": round(
            sum(bool(item.website_url) for item in merchants) / len(merchants) * 100, 2
        ) if merchants else 0.0,
        "merchant_with_item_count_count": sum(item.item_count is not None for item in merchants),
        "wine_signal_count": sum(item.wine_signal for item in merchants),
        "mean_elapsed_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "median_elapsed_ms": round(statistics.median(latencies), 2) if latencies else None,
        "p95_elapsed_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2) if latencies else None,
        "response_bytes_total": sum(item.response_bytes for item in results),
        "sample_merchants": [
            {
                "requested_id": item.requested_id,
                "final_url": item.final_url,
                "name": item.name,
                "merchant_types": item.merchant_types,
                "website_url": item.website_url,
                "item_count": item.item_count,
                "wine_signal_score": item.wine_signal_score,
            }
            for item in merchants[:20]
        ],
        "collection_policy": {
            "public_pages_only": True,
            "authenticated_access": False,
            "captcha_bypass": False,
            "rate_limited": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--pilot-count", type=int, default=30)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--min-interval", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/wine-searcher-poc"))
    args = parser.parse_args()

    if args.start < 1 or args.count < 1:
        parser.error("--start and --count must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    all_ids = list(range(args.start, args.start + args.count))
    pilot_ids = all_ids[: min(args.pilot_count, len(all_ids))]

    print(
        f"Starting pilot: ids={pilot_ids[0]}..{pilot_ids[-1]} count={len(pilot_ids)} "
        f"workers={args.workers} min_interval={args.min_interval}s",
        flush=True,
    )
    pilot_results = collect_ids(
        pilot_ids,
        workers=args.workers,
        min_interval=args.min_interval,
        timeout=args.timeout,
        retries=args.retries,
    )
    pilot_ok, pilot_reason = pilot_is_safe(pilot_results)
    print(f"Pilot decision: ok={pilot_ok} reason={pilot_reason}", flush=True)

    results = pilot_results
    if pilot_ok and len(pilot_ids) < len(all_ids):
        remaining_ids = all_ids[len(pilot_ids) :]
        print(
            f"Continuing full PoC: ids={remaining_ids[0]}..{remaining_ids[-1]} count={len(remaining_ids)}",
            flush=True,
        )
        results.extend(
            collect_ids(
                remaining_ids,
                workers=args.workers,
                min_interval=args.min_interval,
                timeout=args.timeout,
                retries=args.retries,
            )
        )
        results.sort(key=lambda item: item.requested_id)

    finished_at = datetime.now(timezone.utc)
    summary = make_summary(
        results,
        start_id=args.start,
        requested_count=args.count,
        pilot_count=len(pilot_ids),
        pilot_ok=pilot_ok,
        pilot_reason=pilot_reason,
        started_at=started_at,
        finished_at=finished_at,
    )

    csv_path = args.output_dir / "wine_searcher_merchants.csv"
    db_path = args.output_dir / "wine_searcher_merchants.sqlite"
    summary_path = args.output_dir / "summary.json"
    errors_path = args.output_dir / "errors.jsonl"

    write_csv(csv_path, results)
    write_sqlite(db_path, results)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with errors_path.open("w", encoding="utf-8") as handle:
        for item in results:
            if item.result_status not in {"merchant", "not_found", "gone"}:
                handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"Wrote {csv_path}, {db_path}, {summary_path}, {errors_path}", flush=True)

    # A blocked/unstable pilot is a meaningful PoC result, not a workflow crash.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
