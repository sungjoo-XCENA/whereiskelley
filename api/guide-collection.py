import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA_DIR = ROOT / "public" / "data"


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


def read_public_json(name, fallback):
    path = PUBLIC_DATA_DIR / name
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def local_base():
    return os.environ.get("WHEREISKELLEY_LOCAL_API_BASE", "").rstrip("/")


def local_token():
    return os.environ.get("WHEREISKELLEY_LOCAL_API_TOKEN", "").strip()


def local_timeout():
    try:
        return max(5, int(os.environ.get("WHEREISKELLEY_LOCAL_API_TIMEOUT", "60")))
    except ValueError:
        return 60


def proxy_json(path, query=""):
    base = local_base()
    if not base:
        return None
    url = f"{base}{path}"
    if query:
        url = f"{url}?{query}"
    headers = {
        "accept": "application/json",
        "user-agent": "whereiskelley-vercel-proxy/1.0",
    }
    token = local_token()
    if token:
        headers["x-whereiskelley-token"] = token
    request = Request(url, headers=headers)
    with urlopen(request, timeout=local_timeout()) as response:
        return json.loads(response.read().decode("utf-8") or "null")


def static_snapshot_payload(local_error=""):
    status = read_public_json("guide-status.json", {}) or {}
    progress_file = read_public_json("guide-progress.json", {}) or {}
    targets = read_public_json("guide-targets.json", []) or []
    hits = read_public_json("guide-watch-hits.json", []) or []
    counts = status.get("counts") or {}
    last_run = status.get("lastRun") or {}

    target_total = int(counts.get("targets") or last_run.get("target_count") or len(targets) or 0)
    checked = int(last_run.get("websites_checked") or progress_file.get("websitesChecked") or 0)
    sources = int(counts.get("sources") or last_run.get("wine_lists_found") or 0)
    found = int(counts.get("found") or 0)
    review = int(counts.get("review") or 0)
    wine_lines = int(counts.get("wineLines") or last_run.get("wine_lines_found") or 0)
    errors = int(last_run.get("errors") or progress_file.get("errors") or 0)
    no_wine_list = sum(1 for item in targets if item.get("status") == "no_wine_list")
    pending = max(0, target_total - checked)

    map_targets = []
    for index, item in enumerate(targets):
        lat = item.get("lat")
        lng = item.get("lng")
        if lat is None or lng is None:
            continue
        map_targets.append(
            {
                "id": item.get("id") or index,
                "name": item.get("name"),
                "city": item.get("city"),
                "country": item.get("country"),
                "address": item.get("address"),
                "lat": lat,
                "lng": lng,
                "websiteUrl": item.get("website_url") or item.get("websiteUrl") or "",
                "status": item.get("status") or "not_checked",
                "lastCheckedAt": item.get("last_checked_at"),
                "lastError": item.get("last_error"),
                "wineListUrl": item.get("wine_list_url") or item.get("wineListUrl") or "",
                "wineListType": item.get("wine_list_type") or item.get("wineListType") or "",
                "wineListStatus": item.get("wine_list_status") or item.get("wineListStatus") or item.get("status"),
                "wineListParserStatus": item.get("wine_list_parser_status") or item.get("wineListParserStatus") or "",
                "chosenWineLineCount": int(item.get("chosen_wine_line_count") or item.get("chosenWineLineCount") or 0),
                "wineListCount": int(item.get("wine_list_count") or item.get("wineListCount") or 0),
                "verifiedWineListCount": int(item.get("verified_wine_list_count") or item.get("verifiedWineListCount") or 0),
                "reviewSourceCount": int(item.get("review_source_count") or item.get("reviewSourceCount") or 0),
                "wineLineCount": int(item.get("wine_line_count") or item.get("wineLineCount") or 0),
            }
        )

    completed = last_run.get("status") == "completed"
    progress = {
        "generatedAt": status.get("generatedAt") or progress_file.get("generatedAt"),
        "status": "completed" if completed else progress_file.get("status", "ready"),
        "phase": "completed" if completed else progress_file.get("phase", "ready"),
        "message": "Static dashboard snapshot bundled with the deployed app.",
        "runId": last_run.get("id") or progress_file.get("runId"),
        "currentTarget": "",
        "currentUrl": "",
        "targetsCollected": target_total,
        "processedTargets": checked,
        "websitesChecked": checked,
        "totalWebsites": int(last_run.get("target_count") or progress_file.get("totalWebsites") or target_total),
        "wineListsFound": int(last_run.get("wine_lists_found") or sources),
        "wineLinesFound": wine_lines,
        "errors": errors,
        "startedAt": last_run.get("started_at") or progress_file.get("startedAt"),
        "finishedAt": last_run.get("finished_at") or progress_file.get("finishedAt"),
        "durationSeconds": progress_file.get("durationSeconds"),
        "progressPercent": 100 if completed else progress_file.get("progressPercent", 0),
        "dbCounts": {
            "targets": target_total,
            "withWebsite": sum(1 for item in targets if (item.get("website_url") or item.get("websiteUrl"))),
            "wineListSources": sources,
            "wineLines": wine_lines,
            "review": review,
        },
    }
    return {
        "generatedAt": status.get("generatedAt") or progress_file.get("generatedAt"),
        "progress": progress,
        "snapshot": status,
        "guideHits": hits if isinstance(hits, list) else [],
        "counts": progress["dbCounts"],
        "statusCounts": [],
        "sourceStatusCounts": [],
        "collectionSummary": {
            "totalTargets": target_total,
            "checkedTargets": checked,
            "foundWineList": found,
            "noWineList": no_wine_list,
            "pending": pending,
            "missingWebsite": 0,
            "needsReview": review + errors,
            "errors": errors,
            "parseReviewSources": review,
            "parsedSources": found,
            "emptyParsedSources": 0,
            "mappedTargets": len(map_targets),
            "mappedWithWebsite": sum(1 for item in map_targets if item.get("websiteUrl")),
            "totalSources": sources,
        },
        "mapTargets": map_targets,
        "source": "public_snapshot",
        "localApiError": local_error,
    }


def payload():
    local_error = ""
    firebase_error = ""
    try:
        local_payload = proxy_json("/api/guide-collection")
    except Exception as exc:
        local_payload = None
        local_error = str(exc)
    if local_payload is not None:
        if isinstance(local_payload, dict):
            local_payload.setdefault("source", "local_api")
        return local_payload
    try:
        progress = fetch_firebase("progress") or {}
        if isinstance(progress, dict) and (progress.get("collectionSummary") or progress.get("mapTargets")):
            progress.setdefault("source", "firebase")
            return progress
        result = fetch_firebase("result") or {}
        if isinstance(result, dict) and (result.get("collectionSummary") or result.get("mapTargets")):
            result.setdefault("source", "firebase_result")
            return result
    except Exception as exc:
        progress = {}
        result = {}
        firebase_error = str(exc)
    static_payload = static_snapshot_payload(local_error)
    if static_payload.get("collectionSummary", {}).get("totalTargets") or static_payload.get("counts", {}).get("targets"):
        if firebase_error:
            static_payload["firebaseError"] = firebase_error
        return static_payload
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
