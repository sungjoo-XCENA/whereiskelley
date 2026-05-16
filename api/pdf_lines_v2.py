import io
import json
import re
import unicodedata
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader
from search_v2 import PRICE_CURRENCY_RE, parse_price


PRICE_TOKEN_RE = re.compile(
    rf"(?:{PRICE_CURRENCY_RE})?\s*(?:\d{{1,3}}(?:[,\s.]\d{{3}})+|\d{{2,6}}[oO]\s*[,\.]\s*[oO0]{{2}}|\d{{2,6}}(?:\s*[,\.]\s*[oO0]{{2}})?)(?!\d)",
    re.I,
)


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def resolve_pdf_url(url):
    match = re.search(r"drive\.google\.com/file/d/([^/]+)", url or "")
    if match:
        return f"https://drive.google.com/uc?export=download&id={match.group(1)}"
    return url


def fetch_pdf(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "application/pdf,*/*",
        "Referer": "https://starwinelist.com/",
    }
    with urlopen(Request(resolve_pdf_url(url), headers=headers), timeout=25) as response:
        body = response.read()
    if not body.startswith(b"%PDF"):
        raise RuntimeError("PDF response was not a PDF file")
    return body


def extract_text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fold_text(value):
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def clean_fragment(value):
    text = re.sub(r"(?<=\d)(?=[A-Z][a-z])", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def query_tokens(query):
    return [fold_text(token.strip()) for token in query.split() if len(token.strip()) >= 2]


def matching_positions(raw, tokens):
    if not tokens:
        return [0]
    folded = fold_text(raw)
    primary = tokens[0]
    positions = []
    cursor = 0
    while True:
        position = folded.find(primary, cursor)
        if position < 0:
            break
        window = folded[max(0, position - 40) : position + 260]
        if all(token in window for token in tokens):
            positions.append(position)
        cursor = position + max(1, len(primary))
    return positions


def is_probable_wine_row(line, has_price=False):
    text = line.strip()
    return (
        has_price
        or re.search(r"^(?:NV|MV|N/V|\d{4})\b", text, re.I)
        or (text.count(",") >= 2 and len(text) <= 180)
    )


def matched_fragments(raw, query, country):
    tokens = query_tokens(query)
    if tokens and not all(token in fold_text(raw) for token in tokens):
        return []
    fragments = []
    for position in matching_positions(raw, tokens):
        after_limit = min(len(raw), position + 320)
        for match in PRICE_TOKEN_RE.finditer(raw, position, after_limit):
            fragment = raw[position : match.end()]
            price_text, price_value, currency = parse_price(fragment, country, require_edge=True)
            if price_value is not None:
                fragments.append((clean_fragment(fragment), price_text, price_value, currency))
                break
        else:
            fragment = raw[max(0, position - 40) : min(len(raw), position + 220)]
            price_text, price_value, currency = parse_price(fragment, country, require_edge=True)
            fragments.append((clean_fragment(fragment), price_text, price_value, currency))
    unique = []
    seen = set()
    for fragment in fragments:
        key = (fragment[0], fragment[1])
        if key not in seen:
            seen.add(key)
            unique.append(fragment)
    return unique


def match_lines(text, query, country, limit=200):
    matches = []
    for index, raw in enumerate(line.strip() for line in (text or "").splitlines()):
        if not raw:
            continue
        for fragment_index, (fragment, price_text, price_value, currency) in enumerate(matched_fragments(raw, query, country)):
            if not is_probable_wine_row(fragment, price_value is not None):
                continue
            vintage_match = re.search(r"\b(19|20)\d{2}\b", fragment)
            matches.append(
                {
                    "id": f"pdf-{index}-{fragment_index}",
                    "text": fragment,
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
        if len(matches) >= limit:
            break
    return matches


def handle(params):
    file_url = (params.get("fileUrl", [""])[0] or "").strip()
    fallback_urls = [
        url.strip()
        for url in (params.get("fallbackUrls", [""])[0] or "").split("|")
        if url.strip()
    ]
    query = (params.get("q", [""])[0] or "").strip()
    country = (params.get("country", [""])[0] or "").strip()
    candidate_urls = [file_url, *fallback_urls]
    if not any(candidate_urls):
        return {"status": "review", "reason": "No PDF URL available.", "lines": []}
    errors = []
    for url in candidate_urls:
        if not url:
            continue
        try:
            text = extract_text(fetch_pdf(url))
        except Exception as exc:
            errors.append(str(exc))
            continue
        if not text.strip():
            errors.append("PDF has no extractable text. OCR review required.")
            continue
        lines = match_lines(text, query, country)
        if lines:
            return {"status": "ok", "reason": "", "lines": lines}
        errors.append("No matching text found in extracted PDF text.")
    return {
        "status": "review",
        "reason": " ".join(dict.fromkeys(errors)) or "PDF text extraction failed. OCR review required.",
        "lines": [],
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = handle(parse_qs(urlparse(self.path).query))
        json_response(self, payload)
