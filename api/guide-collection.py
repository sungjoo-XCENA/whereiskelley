import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote
from urllib.request import Request, urlopen


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def firebase_url(path):
    base = os.environ.get("FIREBASE_DATABASE_URL", "").rstrip("/")
    if not base:
        return ""
    root = os.environ.get("FIREBASE_COLLECTION_PATH", "whereiskelley/guideCollection").strip("/")
    full_path = "/".join(part.strip("/") for part in [root, path.strip("/")] if part.strip("/"))
    encoded = "/".join(quote(part, safe="") for part in full_path.split("/"))
    url = f"{base}/{encoded}.json"
    token = os.environ.get("FIREBASE_AUTH_TOKEN", "").strip()
    if token:
        url = f"{url}?auth={quote(token, safe='')}"
    return url


def fetch_firebase(path):
    url = firebase_url(path)
    if not url:
        return None
    request = Request(url, headers={"accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8") or "null")


def payload():
    progress = fetch_firebase("progress") or {}
    result = fetch_firebase("result") or {}
    status = result.get("guide_status") or result.get("guide-status") or {}
    hits = result.get("guide_watch_hits") or result.get("guide-watch-hits") or []
    return {
        "generatedAt": progress.get("generatedAt") or result.get("completedAt"),
        "progress": progress,
        "snapshot": status,
        "guideHits": hits if isinstance(hits, list) else [],
        "counts": progress.get("dbCounts") or result.get("dbCounts") or {},
        "source": "firebase" if os.environ.get("FIREBASE_DATABASE_URL") else "not_configured",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            json_response(self, payload())
        except Exception as exc:
            json_response(self, {"error": str(exc), "source": "firebase"}, status=500)
