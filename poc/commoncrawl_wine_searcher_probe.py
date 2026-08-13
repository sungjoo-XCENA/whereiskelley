#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from urllib.parse import urlencode

import requests

COLLINFO = "https://index.commoncrawl.org/collinfo.json"
KNOWN_IDS = (108376, 33938, 19478, 99984)
HOSTS = ("www.wine-searcher.com", "wine-searcher.com")


def decode_lines(response: requests.Response) -> list[dict]:
    out: list[dict] = []
    for line in response.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def query(session: requests.Session, api: str, host: str, merchant_id: int) -> tuple[requests.Response, list[dict], str]:
    params = [
        ("url", f"{host}/merchant/{merchant_id}"),
        ("matchType", "prefix"),
        ("output", "json"),
        ("filter", "status:200"),
        ("limit", "20"),
    ]
    url = api + "?" + urlencode(params)
    response = session.get(url, timeout=60)
    return response, decode_lines(response), url


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": "whereiskelley-commoncrawl-poc/0.2 (public archive research)"})
    coll = session.get(COLLINFO, timeout=30)
    print("collinfo", coll.status_code, len(coll.content), flush=True)
    coll.raise_for_status()
    indexes = coll.json()

    total_found = 0
    for info in indexes[:30]:
        crawl_id = info.get("id")
        api = info["cdx-api"]
        crawl_found = 0
        for merchant_id in KNOWN_IDS:
            for host in HOSTS:
                try:
                    response, records, url = query(session, api, host, merchant_id)
                    merchant_records = [
                        rec for rec in records
                        if re_match_merchant(rec.get("url", ""), merchant_id)
                    ]
                    if merchant_records:
                        samples = [
                            {key: rec.get(key) for key in ("url", "timestamp", "filename", "offset", "length", "status", "mime")}
                            for rec in merchant_records[:3]
                        ]
                        print(json.dumps({
                            "crawl": crawl_id,
                            "host": host,
                            "merchant_id": merchant_id,
                            "http_status": response.status_code,
                            "records": len(merchant_records),
                            "sample": samples,
                        }, ensure_ascii=False), flush=True)
                        crawl_found += len(merchant_records)
                        total_found += len(merchant_records)
                    elif response.status_code not in (200, 404):
                        print(json.dumps({
                            "crawl": crawl_id,
                            "host": host,
                            "merchant_id": merchant_id,
                            "http_status": response.status_code,
                            "response_prefix": response.text[:180],
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:
                    print(json.dumps({
                        "crawl": crawl_id,
                        "host": host,
                        "merchant_id": merchant_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    }, ensure_ascii=False), flush=True)
                time.sleep(0.35)
        print(json.dumps({"crawl": crawl_id, "crawl_found": crawl_found, "total_found": total_found}), flush=True)
        if total_found >= 4:
            break
    print(json.dumps({"probe_complete": True, "total_known_capture_records": total_found}), flush=True)
    return 0


def re_match_merchant(url: str, merchant_id: int) -> bool:
    return f"/merchant/{merchant_id}" in url


if __name__ == "__main__":
    raise SystemExit(main())
