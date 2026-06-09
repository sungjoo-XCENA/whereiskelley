import io
import html as html_lib
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pypdf import PdfReader
from search_v2 import PRICE_CURRENCY_RE, parse_price


PRICE_TOKEN_RE = re.compile(
    rf"(?:{PRICE_CURRENCY_RE})?\s*(?:\d{{1,3}}(?:[,\s.]\s*\d{{3}})+|\d{{2,6}}[oO]\s*[,\.]\s*[oO0]{{2}}|\d{{2,6}}(?:\s*[,\.]\s*[oO0]{{2}})?)(?!\d)",
    re.I,
)
VINTAGE_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


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


def fetch_body(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "application/pdf,text/html,application/xhtml+xml,*/*",
        "Referer": "https://starwinelist.com/",
    }
    with urlopen(Request(resolve_pdf_url(url), headers=headers), timeout=25) as response:
        content_type = response.headers.get("content-type", "")
        body = response.read()
    return body, content_type


def extract_text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "noscript"}:
            self.skip_depth += 1
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        if data and data.strip():
            self.parts.append(data)
            self.parts.append(" ")

    def text(self):
        text = html_lib.unescape("".join(self.parts))
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        return re.sub(r"\n\s*\n+", "\n", text)


def html_to_text(raw_html):
    parser = HTMLTextExtractor()
    parser.feed(raw_html or "")
    return parser.text()


def document_text(url):
    body, content_type = fetch_body(url)
    if body.startswith(b"%PDF") or "pdf" in content_type.lower():
        return "pdf", extract_text(body), ""
    raw_html = body.decode("utf-8", "replace")
    return "html", html_to_text(raw_html), raw_html


def fold_text(value):
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def clean_fragment(value):
    text = re.sub(r"(?<=\d)(?=[^\W\d_])", " ", value or "")
    text = re.sub(r"(?<=[^\W\d_])(?=\d)", " ", text)
    text = re.sub(r"\b(.{3,80}?)\1\b", r"\1", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def display_fragment(value, raw_price="", price_text=""):
    fragment = clean_fragment(value)
    if raw_price and price_text:
        fragment = re.sub(rf"{re.escape(raw_price.strip())}\s*$", price_text, fragment)
    return fragment


def query_tokens(query):
    return [fold_text(token.strip()) for token in query.split() if len(token.strip()) >= 2]


def decode_jsonish_string(value):
    if value is None:
        return ""
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return value.replace(r"\"", '"').replace(r"\\", "\\")


def first_jsonish_string(block, name):
    match = re.search(rf'"{re.escape(name)}"\s*:\s*"((?:\\.|[^"])*)"', block)
    return decode_jsonish_string(match.group(1)) if match else ""


def first_jsonish_array_value(block, name):
    match = re.search(rf'"{re.escape(name)}"\s*:\s*\[\s*"((?:\\.|[^"])*)"', block)
    return decode_jsonish_string(match.group(1)) if match else ""


def jsonish_html_matches(raw_html, query, country, limit=200):
    if not raw_html:
        return []
    source = html_lib.unescape(raw_html)
    quote_placeholder = "\ue000"
    source = re.sub(r'\\{3}"', quote_placeholder, source)
    source = source.replace(r"\"", '"')
    source = source.replace(quote_placeholder, r"\"")
    tokens = query_tokens(query)
    matches = []
    seen = set()
    for index, match in enumerate(re.finditer(r'"fields"\s*:\s*\{(.*?)\}\s*\}', source, re.S)):
        block = match.group(1)
        searchable = fold_text(block)
        if tokens and not all(token in searchable for token in tokens):
            continue
        price_match = re.search(r'"Price"\s*:\s*(\d+(?:\.\d+)?)', block)
        if not price_match:
            continue
        price_text, price_value, currency = parse_price(price_match.group(1), country, require_edge=False)
        if price_value is None:
            continue
        producer = first_jsonish_array_value(block, "Producer Name") or first_jsonish_string(block, "producer")
        name = first_jsonish_string(block, "Name") or first_jsonish_string(block, "name")
        vintage = first_jsonish_string(block, "Vintage") or first_jsonish_string(block, "vintage")
        subregion = first_jsonish_array_value(block, "Subregion") or first_jsonish_string(block, "subregion")
        region = first_jsonish_array_value(block, "Region Name") or first_jsonish_string(block, "region")
        parts = [part for part in [producer, subregion, vintage, name] if part]
        text = ", ".join(parts) or clean_fragment(block[:180])
        key = (fold_text(producer), fold_text(name), vintage, price_value, currency)
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "id": f"html-json-{index}",
                "text": text,
                "vintage": vintage or None,
                "priceValue": price_value,
                "currency": currency,
                "prices": [price_text] if price_text else [],
                "pageNumber": None,
                "review": False,
                "source": "External list verified",
                "region": region,
            }
        )
        if len(matches) >= limit:
            break
    return matches


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


def line_has_tokens(raw, tokens):
    folded = fold_text(raw)
    return bool(tokens) and all(token in folded for token in tokens)


def query_remainder_letters(raw, tokens):
    folded = fold_text(raw)
    for token in tokens:
        folded = folded.replace(token, " ")
    return re.sub(r"[^a-z0-9]", "", folded)


def section_header_limit(raw, tokens):
    if not line_has_tokens(raw, tokens):
        return 0
    if PRICE_TOKEN_RE.search(raw) or re.search(r"\b(?:NV|MV|N/V)\b", raw, re.I) or VINTAGE_RE.search(raw):
        return 0
    remainder = query_remainder_letters(raw, tokens)
    return 30 if len(remainder) >= 4 else 1


def is_probable_wine_row(line, has_price=False):
    text = line.strip()
    return (
        has_price
        or re.search(r"^(?:NV|MV|N/V|\d{4})\b", text, re.I)
        or (text.count(",") >= 2 and len(text) <= 180)
    )


def is_section_price_row(line):
    return (re.search(r"\b(?:NV|MV|N/V)\b", line, re.I) or VINTAGE_RE.search(line)) and PRICE_TOKEN_RE.search(line)


def is_likely_section_break(line):
    text = clean_fragment(line)
    if not text:
        return False
    if is_section_price_row(text):
        return False
    folded = fold_text(text)
    letters = re.sub(r"[^a-z]", "", folded)
    return len(text) <= 90 and len(letters) >= 4 and (
        text.isupper()
        or re.search(r"^(?:francia|france|italia|italy|spain|espana|germany|austria|champagne|burgundy|borgo)", folded, re.I)
    )


def vintage_near(raw, position, fragment):
    fragment_match = VINTAGE_RE.search(fragment or "")
    if fragment_match:
        return fragment_match.group(0)
    window = raw[max(0, position - 120) : min(len(raw), position + 260)]
    window_match = VINTAGE_RE.search(window)
    return window_match.group(0) if window_match else None


def section_row_price(raw, country):
    for match in reversed(list(PRICE_TOKEN_RE.finditer(raw or ""))):
        price_text, price_value, currency = parse_price(match.group(0), country, require_edge=False)
        if price_value is not None:
            return price_text, price_value, currency
    return "", None, None


def section_fragment(header, raw, country):
    if not is_section_price_row(raw):
        return None
    fragment = display_fragment(f"{header}, {raw}")
    price_text, price_value, currency = section_row_price(raw, country)
    if price_value is None:
        price_text, price_value, currency = parse_price(raw, country, require_edge=True)
    if price_value is None:
        price_text, price_value, currency = parse_price(fragment, country, require_edge=False)
    if price_value is None:
        return None
    fragment = display_fragment(f"{header}, {raw}", price_text and re.search(PRICE_TOKEN_RE, raw or "").group(0), price_text)
    vintage = vintage_near(raw, 0, raw) or vintage_near(fragment, 0, fragment)
    return fragment, price_text, price_value, currency, vintage


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
                fragments.append((display_fragment(fragment, match.group(0), price_text), price_text, price_value, currency, vintage_near(raw, position, fragment)))
                break
        else:
            before_start = max(0, position - 90)
            before_matches = list(PRICE_TOKEN_RE.finditer(raw, before_start, position))
            for match in reversed(before_matches):
                fragment = raw[match.start() : min(len(raw), position + 220)]
                price_text, price_value, currency = parse_price(fragment, country, require_edge=False)
                if price_value is not None:
                    fragments.append((display_fragment(fragment, match.group(0), price_text), price_text, price_value, currency, vintage_near(raw, position, fragment)))
                    break
            else:
                fragment = raw[max(0, position - 40) : min(len(raw), position + 220)]
                price_text, price_value, currency = parse_price(fragment, country, require_edge=True)
                fragments.append((display_fragment(fragment), price_text, price_value, currency, vintage_near(raw, position, fragment)))
    unique = []
    seen = set()
    for fragment in fragments:
        key = (fragment[0], fragment[1], fragment[4])
        if key not in seen:
            seen.add(key)
            unique.append(fragment)
    return unique


def match_lines(text, query, country, limit=200):
    matches = []
    tokens = query_tokens(query)
    active_header = ""
    active_remaining = 0
    section_hits = 0
    active_max_hits = 0
    for index, raw in enumerate(line.strip() for line in (text or "").splitlines()):
        if not raw:
            if active_header:
                active_remaining -= 1
                if active_remaining <= 0:
                    active_header = ""
                    section_hits = 0
                    active_max_hits = 0
            continue
        header_limit = section_header_limit(raw, tokens)
        if header_limit:
            active_header = clean_fragment(raw)
            active_remaining = 30
            section_hits = 0
            active_max_hits = header_limit
        elif line_has_tokens(raw, tokens):
            active_header = ""
            active_remaining = 0
            section_hits = 0
            active_max_hits = 0
        for fragment_index, (fragment, price_text, price_value, currency, nearby_vintage) in enumerate(matched_fragments(raw, query, country)):
            if not is_probable_wine_row(fragment, price_value is not None):
                continue
            vintage_match = VINTAGE_RE.search(fragment)
            matches.append(
                {
                    "id": f"pdf-{index}-{fragment_index}",
                    "text": fragment,
                    "vintage": nearby_vintage or (vintage_match.group(0) if vintage_match else None),
                    "priceValue": price_value,
                    "currency": currency,
                    "prices": [price_text] if price_text else [],
                    "pageNumber": None,
                    "review": price_value is None,
                }
            )
            if len(matches) >= limit:
                break
        if active_header and not line_has_tokens(raw, tokens):
            section = section_fragment(active_header, raw, country)
            if section:
                fragment, price_text, price_value, currency, nearby_vintage = section
                matches.append(
                    {
                        "id": f"pdf-section-{index}",
                        "text": fragment,
                        "vintage": nearby_vintage,
                        "priceValue": price_value,
                        "currency": currency,
                        "prices": [price_text] if price_text else [],
                        "pageNumber": None,
                        "review": False,
                    }
                )
                section_hits += 1
                if active_max_hits and section_hits >= active_max_hits:
                    active_header = ""
                    active_remaining = 0
                    section_hits = 0
                    active_max_hits = 0
                else:
                    active_remaining = 30
            elif section_hits and is_likely_section_break(raw):
                active_header = ""
                active_remaining = 0
                section_hits = 0
                active_max_hits = 0
            else:
                active_remaining -= 1
                if active_remaining <= 0:
                    active_header = ""
                    section_hits = 0
                    active_max_hits = 0
        if len(matches) >= limit:
            break
    unique = []
    seen = set()
    for item in matches:
        key = (item.get("text"), item.get("vintage"), item.get("priceValue"), item.get("currency"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


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
            kind, text, raw_html = document_text(url)
        except Exception as exc:
            errors.append(str(exc))
            continue
        if not text.strip():
            errors.append("List has no extractable text. OCR or manual review required.")
            continue
        if kind == "html":
            json_lines = jsonish_html_matches(raw_html, query, country)
            lines = json_lines if json_lines else match_lines(text, query, country)
            for line in lines:
                line.setdefault("source", "External list verified")
        else:
            lines = match_lines(text, query, country)
        if lines:
            return {"status": "ok", "reason": "", "lines": lines}
        errors.append("No matching text found in extracted list text.")
    return {
        "status": "review",
        "reason": " ".join(dict.fromkeys(errors)) or "List text extraction failed. OCR or manual review required.",
        "lines": [],
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = handle(parse_qs(urlparse(self.path).query))
        json_response(self, payload)
