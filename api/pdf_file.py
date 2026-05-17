import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_lines_v2 import fetch_pdf


def text_response(handler, text, status=400):
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "text/plain; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_pdf(handler, body, filename):
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename or "wine-list.pdf").strip("-")
    if not safe_name.lower().endswith(".pdf"):
        safe_name = f"{safe_name}.pdf"
    handler.send_response(200)
    handler.send_header("content-type", "application/pdf")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-disposition", f'attachment; filename="{safe_name}"')
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        primary = (params.get("url", [""])[0] or "").strip()
        fallback_urls = [
            url.strip()
            for url in (params.get("fallbackUrls", [""])[0] or "").split("|")
            if url.strip()
        ]
        filename = (params.get("filename", ["wine-list.pdf"])[0] or "wine-list.pdf").strip()
        errors = []
        for url in [primary, *fallback_urls]:
            if not url:
                continue
            try:
                send_pdf(self, fetch_pdf(url), filename)
                return
            except Exception as exc:
                errors.append(str(exc))
        text_response(self, "PDF download failed. " + " ".join(dict.fromkeys(errors)), status=502)
