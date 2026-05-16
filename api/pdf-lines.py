import io
import json
import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search import parse_price


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def fetch_pdf(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "application/pdf,*/*",
        "Referer": "https://starwinelist.com/",
    }
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        body = response.read()
    if not body.startswith(b"%PDF"):
        raise RuntimeError("PDF response was not a PDF file")
    return body


def extract_text(pdf_bytes):
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError(f"pypdf is not available: {exc}") from exc
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def match_lines(text, query, country, limit=200):
    tokens = [token.casefold() for token in query.split() if len(token.strip()) >= 2]
    matches = []
    for index, raw in enumerate(line.strip() for line in (text or "").splitlines()):
        if not raw:
            continue
        folded = raw.casefold()
        if tokens and not all(token in folded for token in tokens):
            continue
        price_text, price_value, currency = parse_price(raw, country)
        vintage_match = re.search(r"\b(19|20)\d{2}\b", raw)
        matches.append(
            {
                "id": f"pdf-{index}",
                "text": raw,
                "vintage": vintage_match.group(0) if vintage_match else None,
                "priceValue": price_value,
                "currency": currency,
                "prices": [price_text] if price_text else [],
                "pageNumber": None,
                "review": price_value is None,
            }
        )
        if len(matches) >= limit:
            break
    return matches


def handle(params):
    file_url = (params.get("fileUrl", [""])[0] or "").strip()
    query = (params.get("q", [""])[0] or "").strip()
    country = (params.get("country", [""])[0] or "").strip()
    if not file_url:
        return {"status": "review", "reason": "No PDF URL available.", "lines": []}
    try:
        text = extract_text(fetch_pdf(file_url))
    except Exception as exc:
        return {"status": "review", "reason": f"PDF text extraction failed. OCR review required. {exc}", "lines": []}
    if not text.strip():
        return {"status": "review", "reason": "PDF has no extractable text. OCR review required.", "lines": []}
    lines = match_lines(text, query, country)
    return {
        "status": "ok" if lines else "review",
        "reason": "" if lines else "No matching text found in extracted PDF text.",
        "lines": lines,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = handle(parse_qs(urlparse(self.path).query))
        json_response(self, payload)
