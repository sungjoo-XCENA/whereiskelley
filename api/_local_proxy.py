import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def local_base():
    return os.environ.get("WHEREISKELLEY_LOCAL_API_BASE", "").rstrip("/")


def local_token():
    return os.environ.get("WHEREISKELLEY_LOCAL_API_TOKEN", "").strip()


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def proxy_json(path, query=""):
    base = local_base()
    if not base:
        return None
    url = f"{base}{path}"
    if query:
        url = f"{url}?{query}"
    headers = {"accept": "application/json"}
    token = local_token()
    if token:
        headers["x-whereiskelley-token"] = token
    request = Request(url, headers=headers)
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8") or "null")


def proxy_or_error(handler, path, query=""):
    try:
        payload = proxy_json(path, query)
        if payload is None:
            return json_response(
                handler,
                {
                    "error": "Local API is not configured.",
                    "source": "local_api_not_configured",
                },
                status=503,
            )
        if isinstance(payload, dict):
            payload.setdefault("source", "local_api")
        return json_response(handler, payload)
    except Exception as exc:
        return json_response(
            handler,
            {"error": str(exc), "source": "local_api_unreachable"},
            status=502,
        )
