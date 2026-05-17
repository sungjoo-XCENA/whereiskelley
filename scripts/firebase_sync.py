import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen


def enabled():
    return bool(os.environ.get("FIREBASE_DATABASE_URL"))


def firebase_url(path):
    base = os.environ.get("FIREBASE_DATABASE_URL", "").rstrip("/")
    root = os.environ.get("FIREBASE_COLLECTION_PATH", "whereiskelley/guideCollection").strip("/")
    full_path = "/".join(part.strip("/") for part in [root, path.strip("/")] if part.strip("/"))
    encoded = "/".join(quote(part, safe="") for part in full_path.split("/"))
    url = f"{base}/{encoded}.json"
    token = os.environ.get("FIREBASE_AUTH_TOKEN", "").strip()
    if token:
        url = f"{url}?auth={quote(token, safe='')}"
    return url


def put(path, payload, timeout=8):
    if not enabled():
        return False
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        firebase_url(path),
        data=body,
        method="PUT",
        headers={"content-type": "application/json; charset=utf-8"},
    )
    with urlopen(request, timeout=timeout) as response:
        response.read()
    return True


def publish_progress(payload):
    try:
        return put("progress", payload)
    except Exception:
        return False


def publish_result(payload):
    try:
        return put("result", payload)
    except Exception:
        return False
