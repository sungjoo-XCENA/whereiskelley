#!/usr/bin/env python3
from __future__ import annotations

import json
from urllib.parse import urlencode

import requests

ENDPOINT = "https://web.archive.org/cdx/search/cdx"


def main() -> int:
    params = [
        ("url", "www.wine-searcher.com/merchant/"),
        ("matchType", "prefix"),
        ("output", "json"),
        ("fl", "timestamp,original,statuscode,mimetype,digest"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "urlkey"),
        ("limit", "1200"),
    ]
    url = ENDPOINT + "?" + urlencode(params)
    session = requests.Session()
    session.headers.update({"User-Agent": "whereiskelley-archive-poc/0.1"})
    response = session.get(url, timeout=120)
    print(json.dumps({
        "status": response.status_code,
        "bytes": len(response.content),
        "url": url,
        "prefix": response.text[:300] if response.status_code != 200 else "",
    }, ensure_ascii=False), flush=True)
    if response.status_code != 200:
        return 0
    try:
        rows = response.json()
    except Exception as exc:
        print(json.dumps({"parse_error": f"{type(exc).__name__}: {exc}", "prefix": response.text[:500]}), flush=True)
        return 0
    if not rows:
        print(json.dumps({"records": 0}), flush=True)
        return 0
    header = rows[0]
    records = [dict(zip(header, row)) for row in rows[1:]]
    merchant_records = [r for r in records if "/merchant/" in r.get("original", "")]
    ids = set()
    for record in merchant_records:
        import re
        m = re.search(r"/merchant/(\d+)", record.get("original", ""))
        if m:
            ids.add(int(m.group(1)))
    print(json.dumps({
        "records": len(records),
        "merchant_records": len(merchant_records),
        "unique_merchant_ids": len(ids),
        "min_id": min(ids) if ids else None,
        "max_id": max(ids) if ids else None,
        "sample": merchant_records[:10],
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
