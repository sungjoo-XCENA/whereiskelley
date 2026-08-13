#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

ENDPOINT = "https://web.archive.org/cdx/search/cdx"
OUTDIR = Path("artifacts/wine-searcher-wayback-index")


def merchant_id(url: str):
    m = re.search(r"/merchant/0*(\d+)(?:[-/?#]|$)", url, re.I)
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def clean_profile(url: str) -> bool:
    p = urlparse(url)
    return not p.query and bool(re.fullmatch(r"/merchant/0*\d+(?:-[^/?#]+)?/?", p.path, re.I))


def main():
    params = [
        ("url", "www.wine-searcher.com/merchant/"),
        ("matchType", "prefix"),
        ("output", "json"),
        ("fl", "timestamp,original,statuscode,mimetype,digest"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("from", "2023"),
        ("to", "2026"),
        ("collapse", "urlkey"),
        ("limit", "30000"),
    ]
    url = ENDPOINT + "?" + urlencode(params)
    r = requests.get(url, timeout=180, headers={"User-Agent": "whereiskelley-wayback-index-poc/0.2"})
    print("status", r.status_code, "bytes", len(r.content), flush=True)
    r.raise_for_status()
    raw = r.json()
    header = raw[0]
    rows = [dict(zip(header, row)) for row in raw[1:]]
    chosen = {}
    for row in rows:
        original = row.get("original", "")
        mid = merchant_id(original)
        if mid is None or not clean_profile(original):
            continue
        prev = chosen.get(mid)
        if prev is None or row.get("timestamp", "") > prev.get("timestamp", ""):
            chosen[mid] = {"merchant_id": mid, **row}
    selected = sorted(chosen.values(), key=lambda x: x["merchant_id"])[:1000]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    columns = ["merchant_id", "timestamp", "original", "statuscode", "mimetype", "digest"]
    with (OUTDIR / "merchant_capture_index_1000.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(selected)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "query_from_year": 2023,
        "query_to_year": 2026,
        "cdx_records_received": len(rows),
        "unique_clean_merchant_ids": len(chosen),
        "exported_count": len(selected),
        "min_id": min((x["merchant_id"] for x in selected), default=None),
        "max_id": max((x["merchant_id"] for x in selected), default=None),
        "capture_year_counts": {},
    }
    for row in selected:
        year = row.get("timestamp", "")[:4]
        summary["capture_year_counts"][year] = summary["capture_year_counts"].get(year, 0) + 1
    (OUTDIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
