#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from urllib.parse import urlencode

import requests

COLLINFO = "https://index.commoncrawl.org/collinfo.json"


def main() -> int:
    s = requests.Session()
    s.headers.update({"User-Agent": "whereiskelley-commoncrawl-poc/0.1 (public archive research)"})
    coll = s.get(COLLINFO, timeout=30)
    print("collinfo", coll.status_code, len(coll.content), flush=True)
    coll.raise_for_status()
    indexes = coll.json()
    for info in indexes[:12]:
        api = info["cdx-api"]
        params = [
            ("url", "www.wine-searcher.com/merchant/*"),
            ("output", "json"),
            ("filter", "status:200"),
            ("filter", "mime:text/html"),
            ("collapse", "urlkey"),
            ("limit", "1200"),
        ]
        url = api + "?" + urlencode(params)
        try:
            r = s.get(url, timeout=90)
            lines = [line for line in r.text.splitlines() if line.strip()]
            good = 0
            sample = []
            for line in lines:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if "/merchant/" in rec.get("url", ""):
                    good += 1
                    if len(sample) < 3:
                        sample.append({k: rec.get(k) for k in ("url", "timestamp", "filename", "offset", "length", "status")})
            print(json.dumps({
                "id": info.get("id"),
                "status": r.status_code,
                "bytes": len(r.content),
                "lines": len(lines),
                "merchant_records": good,
                "sample": sample,
                "response_prefix": r.text[:300] if r.status_code != 200 else "",
            }, ensure_ascii=False), flush=True)
            if good >= 1000:
                return 0
        except Exception as exc:
            print(json.dumps({"id": info.get("id"), "error": f"{type(exc).__name__}: {exc}"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
