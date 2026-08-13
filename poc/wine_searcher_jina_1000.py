#!/usr/bin/env python3
"""Collect public Wine-Searcher merchant profiles through Jina Reader.

This fallback is used only because Wine-Searcher returns HTTP 403 to common
cloud-runner IPs. It still reads public profile pages only and does not access
logged-in or PRO-only content.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

TARGET = "https://www.wine-searcher.com/merchant/{merchant_id}"
READER = "https://r.jina.ai/http://www.wine-searcher.com/merchant/{merchant_id}"


@dataclass
class Row:
    requested_id: int
    target_url: str
    reader_url: str
    result_status: str
    reader_status_code: int | None = None
    target_status_code: int | None = None
    canonical_url: str = ""
    final_id: int | None = None
    slug: str = ""
    name: str = ""
    merchant_types: str = ""
    website_url: str = ""
    website_domain: str = ""
    item_count: int | None = None
    price_list_collected: str = ""
    business_listed_since: str = ""
    country_region: str = ""
    address: str = ""
    phone: str = ""
    wine_signal: int = 0
    elapsed_ms: int = 0
    response_bytes: int = 0
    error: str = ""


class Limiter:
    def __init__(self, interval: float):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)
        time.sleep(random.uniform(0.03, 0.12))


local = threading.local()


def session() -> requests.Session:
    s = getattr(local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": "whereiskelley-public-merchant-poc/0.1",
                "Accept": "text/plain,text/markdown;q=0.9,*/*;q=0.1",
                "X-Return-Format": "markdown",
                "X-Retain-Images": "none",
                "X-With-Generated-Alt": "false",
            }
        )
        local.s = s
    return s


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def capture(pattern: str, text: str, flags=re.I | re.M) -> str:
    m = re.search(pattern, text, flags)
    return clean(m.group(1)) if m else ""


def parse_target_status(text: str, response: requests.Response) -> int | None:
    for key in ("x-target-status-code", "x-target-status", "x-origin-status"):
        value = response.headers.get(key)
        if value and str(value).isdigit():
            return int(value)
    m = re.search(r"Target URL returned error\s+(\d{3})", text, re.I)
    return int(m.group(1)) if m else None


def parse_identity(url: str) -> tuple[int | None, str]:
    m = re.search(r"/merchant/(\d+)(?:-([^/?#]+))?", url)
    return (int(m.group(1)), m.group(2) or "") if m else (None, "")


def parse_row(mid: int, response: requests.Response, elapsed_ms: int) -> Row:
    text = response.text
    row = Row(
        requested_id=mid,
        target_url=TARGET.format(merchant_id=mid),
        reader_url=READER.format(merchant_id=mid),
        result_status="unknown",
        reader_status_code=response.status_code,
        elapsed_ms=elapsed_ms,
        response_bytes=len(response.content),
    )
    row.target_status_code = parse_target_status(text, response)

    if response.status_code == 429:
        row.result_status = "reader_rate_limited"
        return row
    if response.status_code in (401, 403):
        row.result_status = "reader_blocked"
        return row
    if response.status_code >= 500:
        row.result_status = "reader_server_error"
        return row
    if response.status_code >= 400:
        row.result_status = "reader_http_error"
        return row
    if row.target_status_code in (404, 410):
        row.result_status = "not_found"
        return row
    if row.target_status_code in (401, 403):
        row.result_status = "target_blocked"
        return row

    source = capture(r"^URL Source:\s*(\S+)", text)
    if not source:
        source = capture(r"^URL:\s*(\S+)", text)
    row.canonical_url = source or row.target_url
    row.final_id, row.slug = parse_identity(row.canonical_url)

    name = capture(r"^#\s+(.+)$", text)
    if not name:
        title = capture(r"^Title:\s*(.+)$", text)
        name = re.sub(r"\s*[-|]\s*[^-|]*Wine-Searcher.*$", "", title, flags=re.I)
    row.name = clean(name)

    lower = text.lower()
    if not row.name or ("delivery & services" not in lower and "contact details" not in lower and "price list" not in lower):
        if "robots.txt" in lower or "blocked by robots" in lower:
            row.result_status = "robots_blocked"
        elif "target url returned error 404" in lower or "page not found" in lower:
            row.result_status = "not_found"
        else:
            row.result_status = "invalid_page"
        return row

    row.result_status = "merchant"
    type_line = ""
    lines = [clean(line.lstrip("#* -")) for line in text.splitlines()]
    for idx, line in enumerate(lines):
        if line == row.name:
            for candidate in lines[idx + 1 : idx + 8]:
                if candidate and not candidate.startswith(("URL Source", "Markdown Content")):
                    type_line = candidate
                    break
            break
    known = [
        "Retail chain", "Auction house", "Wine Club", "Wholesaler", "Distributor",
        "Retailer", "Producer", "Winery", "Brewery", "Distillery", "Broker", "Importer",
    ]
    hits = [kind for kind in known if re.search(rf"\b{re.escape(kind)}\b", type_line, re.I)]
    if not hits:
        hits = [kind for kind in known if re.search(rf"\b{re.escape(kind)}\b", text[:5000], re.I)]
    row.merchant_types = " · ".join(dict.fromkeys(hits))

    links = re.findall(r"\[[^\]]*(?:website|visit|shop)[^\]]*\]\((https?://[^)]+)\)", text, re.I)
    if not links:
        links = re.findall(r"\((https?://[^)]+)\)", text)
    for url in links:
        host = urlparse(url).netloc.lower()
        if host and "wine-searcher.com" not in host and not any(x in host for x in ("google.", "facebook.", "instagram.", "linkedin.", "twitter.", "x.com")):
            row.website_url = url
            row.website_domain = host
            break

    item = capture(r"([0-9][0-9,]*)\s*(?:items|products)\b", text)
    if item:
        try:
            row.item_count = int(item.replace(",", ""))
        except ValueError:
            pass
    row.price_list_collected = capture(r"Price list collected\s*:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", text)
    row.business_listed_since = capture(r"Business listed since\s+([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", text)

    contact = capture(r"### Contact details\s+(.+?)(?:\n###|\n\* \* \*|$)", text, re.I | re.S)
    contact_lines = [clean(re.sub(r"^[-*#]+", "", x)) for x in contact.splitlines() if clean(x)]
    if contact_lines:
        row.country_region = contact_lines[0][:120]
        if len(contact_lines) > 1:
            row.address = contact_lines[1][:300]
    row.phone = capture(r"(\+?[0-9][0-9 ()\-]{6,}[0-9])", contact)

    wine_score = 0
    if "wines ship" in lower:
        wine_score += 2
    if "wine merchant" in lower:
        wine_score += 2
    if re.search(r"\b(wine|winery|vineyard|vin)\b", f"{row.name} {row.merchant_types}", re.I):
        wine_score += 2
    if row.website_domain and any(k in row.website_domain for k in ("wine", "vin", "cellar")):
        wine_score += 1
    row.wine_signal = int(wine_score >= 2)
    return row


def fetch(mid: int, limiter: Limiter, timeout: int, retries: int) -> Row:
    url = READER.format(merchant_id=mid)
    last_error = ""
    for attempt in range(retries + 1):
        limiter.wait()
        t0 = time.perf_counter()
        try:
            r = session().get(url, timeout=timeout)
            elapsed = int((time.perf_counter() - t0) * 1000)
            row = parse_row(mid, r, elapsed)
            if row.result_status in {"reader_rate_limited", "reader_server_error"} and attempt < retries:
                time.sleep(min(30, 3 * (2 ** attempt) + random.random()))
                continue
            return row
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"[:500]
            if attempt < retries:
                time.sleep(2 ** attempt + random.random())
                continue
            return Row(mid, TARGET.format(merchant_id=mid), url, "request_error", error=last_error)
    return Row(mid, TARGET.format(merchant_id=mid), url, "request_error", error=last_error)


def collect(ids: list[int], workers: int, interval: float, timeout: int, retries: int) -> list[Row]:
    limiter = Limiter(interval)
    out: list[Row] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, mid, limiter, timeout, retries): mid for mid in ids}
        for i, future in enumerate(as_completed(futures), 1):
            mid = futures[future]
            try:
                out.append(future.result())
            except Exception as exc:
                out.append(Row(mid, TARGET.format(merchant_id=mid), READER.format(merchant_id=mid), "worker_error", error=str(exc)[:500]))
            if i <= 10 or i % 25 == 0 or i == len(ids):
                c = Counter(x.result_status for x in out)
                print(f"progress={i}/{len(ids)} merchant={c['merchant']} not_found={c['not_found']} blocked={c['reader_blocked'] + c['target_blocked'] + c['robots_blocked']} rate_limited={c['reader_rate_limited']} invalid={c['invalid_page']}", flush=True)
    return sorted(out, key=lambda x: x.requested_id)


def save(outdir: Path, rows: list[Row], summary: dict):
    outdir.mkdir(parents=True, exist_ok=True)
    columns = [f.name for f in fields(Row)]
    with (outdir / "wine_searcher_merchants_jina.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row in rows:
            w.writerow(asdict(row))
    db = outdir / "wine_searcher_merchants_jina.sqlite"
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    try:
        defs = []
        for col in columns:
            if col in {"requested_id", "reader_status_code", "target_status_code", "final_id", "item_count", "wine_signal", "elapsed_ms", "response_bytes"}:
                defs.append(f"{col} INTEGER")
            else:
                defs.append(f"{col} TEXT")
        conn.execute(f"CREATE TABLE merchants ({', '.join(defs)}, PRIMARY KEY(requested_id))")
        conn.executemany(
            f"INSERT INTO merchants ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [[getattr(row, col) for col in columns] for row in rows],
        )
        conn.execute("CREATE INDEX idx_status ON merchants(result_status)")
        conn.execute("CREATE INDEX idx_domain ON merchants(website_domain)")
        conn.commit()
    finally:
        conn.close()
    (outdir / "summary_jina.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (outdir / "errors_jina.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            if row.result_status not in {"merchant", "not_found"}:
                f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2)
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--pilot", type=int, default=12)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--interval", type=float, default=0.55)
    p.add_argument("--timeout", type=int, default=35)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/wine-searcher-jina-poc"))
    args = p.parse_args()

    started = datetime.now(timezone.utc)
    ids = list(range(args.start, args.start + args.count))
    pilot_ids = ids[: min(args.pilot, len(ids))]
    print(f"Jina pilot ids={pilot_ids[0]}..{pilot_ids[-1]} count={len(pilot_ids)}", flush=True)
    rows = collect(pilot_ids, args.workers, args.interval, args.timeout, args.retries)
    c = Counter(x.result_status for x in rows)
    blocked = c["reader_blocked"] + c["target_blocked"] + c["robots_blocked"]
    unstable = c["reader_rate_limited"] + c["reader_server_error"] + c["request_error"]
    pilot_ok = blocked == 0 and unstable < max(3, len(rows) // 3) and c["merchant"] + c["not_found"] > 0
    reason = "pilot passed" if pilot_ok else f"pilot failed: {dict(c)}"
    print(f"pilot_ok={pilot_ok} reason={reason}", flush=True)

    if pilot_ok and len(pilot_ids) < len(ids):
        rows.extend(collect(ids[len(pilot_ids):], args.workers, args.interval, args.timeout, args.retries))
        rows.sort(key=lambda x: x.requested_id)

    finished = datetime.now(timezone.utc)
    c = Counter(x.result_status for x in rows)
    merchants = [x for x in rows if x.result_status == "merchant"]
    summary = {
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "requested_start_id": args.start,
        "requested_count": args.count,
        "attempted_count": len(rows),
        "pilot_ok": pilot_ok,
        "pilot_reason": reason,
        "result_status_counts": dict(sorted(c.items())),
        "merchant_count": len(merchants),
        "merchant_yield_percent": round(len(merchants) / len(rows) * 100, 2) if rows else 0,
        "merchant_with_website_count": sum(bool(x.website_url) for x in merchants),
        "wine_signal_count": sum(x.wine_signal for x in merchants),
        "sample_merchants": [asdict(x) for x in merchants[:15]],
        "transport": "Jina Reader public URL-to-markdown endpoint",
        "public_pages_only": True,
        "authenticated_access": False,
    }
    save(args.output_dir, rows, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
