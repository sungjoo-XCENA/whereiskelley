import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote
from urllib.request import Request, urlopen

from _local_proxy import proxy_json


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
    local_error = ""
    try:
        local_payload = proxy_json("/api/guide-collection")
    except Exception as exc:
        local_payload = None
        local_error = str(exc)
    if local_payload is not None:
        if isinstance(local_payload, dict):
            local_payload.setdefault("source", "local_api")
        return local_payload
    progress = fetch_firebase("progress") or {}
    if isinstance(progress, dict) and (progress.get("collectionSummary") or progress.get("mapTargets")):
        progress.setdefault("source", "firebase")
        return progress
    result = fetch_firebase("result") or {}
    if isinstance(result, dict) and (result.get("collectionSummary") or result.get("mapTargets")):
        result.setdefault("source", "firebase_result")
        return result
    status = result.get("guide_status") or result.get("guide-status") or {}
    hits = result.get("guide_watch_hits") or result.get("guide-watch-hits") or []
    return {
        "generatedAt": progress.get("generatedAt") or result.get("completedAt"),
        "progress": progress,
        "snapshot": status,
        "guideHits": hits if isinstance(hits, list) else [],
        "counts": progress.get("dbCounts") or result.get("dbCounts") or {},
        "source": "firebase" if os.environ.get("FIREBASE_DATABASE_URL") else "not_configured",
        "localApiError": local_error,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            json_response(self, payload())
        except Exception as exc:
            json_response(self, {"error": str(exc), "source": "firebase"}, status=500)
