import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search as base


PRICE_CURRENCY_RE = base.PRICE_CURRENCY_RE
BASE_NORMALIZE_RESULT = base.normalize_result


def split_collapsed_price(value, raw_number, country, has_currency):
    compact = re.sub(r"\D", "", raw_number or "")
    currency = base.normalize_currency("", country)
    low_denomination = currency in {"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "SGD", "DKK", "SEK", "NOK"}
    if has_currency or not low_denomination or not compact.isdigit() or len(compact) not in {5, 6}:
        return value
    suffix = int(compact[-2:])
    prefix = int(compact[:-2])
    if 100 <= prefix <= 5000 and 1 <= suffix <= 80:
        return float(prefix)
    return value


def parse_price(line, country="", page_number=None, require_edge=False):
    cleaned = base.strip_search_page_suffix(line, page_number)
    no_price = re.search(base.NO_PRICE_RE, cleaned, re.I) is not None
    text = re.sub(r"\b(19|20)\d{2}\b", " ", cleaned)
    text = re.sub(r"\b(?:page|p\.?)\s*\d{1,4}\b", " ", text, flags=re.I)
    text = re.sub(r"\b0\s*[,\.]\s*(?:187|375|5|50|70|75|750|150|1500)\s*(?:l|lt|liter|litre)?\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:37\.?5|75|187|375|500|750|1500)\s*(?:ml|cl)\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{1,3}\s*%\s*", " ", text)
    price_number = r"(?:\d{1,3}(?:[,\s.]\d{3})+|\d{2,6}[oO]\s*[,\.]\s*[oO0]{2}|\d{2,6}(?:\s*[,\.]\s*[oO0]{2})?)"
    patterns = [
        rf"(?<![\w])(?:{PRICE_CURRENCY_RE})\s*{price_number}(?!\d)",
        rf"(?<!\d){price_number}\s*(?:{PRICE_CURRENCY_RE})(?![\w])",
        r"(?<!\d)\d{1,3}(?:,\d{3})+(?:\.\d{2})?(?!\d)",
        r"(?<!\d)\d{1,3}(?:,\s*\d{3})+(?:\.\d{2})?(?!\d)",
        r"(?<!\d)\d{1,3}(?:[ .]\d{3})+(?:,\d{2})?(?!\d)",
        r"(?<!\d)\d{2,6}[oO]\s*[,\.]\s*[oO0]{2}(?!\w)",
        r"(?<!\d)\d{2,6}\s*[,\.]\s*[oO0]{2}(?!\d)",
        r"(?<!\d)\d{2,6}(?!\d)",
    ]
    candidates = []
    used_spans = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if any(match.start() < end and match.end() > start for start, end in used_spans):
                continue
            raw = match.group(0).strip()
            raw_number = re.sub(PRICE_CURRENCY_RE, "", raw, flags=re.I)
            has_currency = re.search(PRICE_CURRENCY_RE, text[max(0, match.start() - 8):match.end() + 8], re.I) is not None
            try:
                value = base.parse_price_number(raw_number)
            except ValueError:
                continue
            value = split_collapsed_price(value, raw_number, country, has_currency)
            if value >= 10:
                tail = re.sub(r"[\s,.;:)\]]+$", "", text[match.end():])
                right_edge = not tail
                candidates.append((match.start(), base.display_price(value), value, right_edge, has_currency))
                used_spans.append(match.span())
    currency_match = re.search(PRICE_CURRENCY_RE, cleaned, re.I)
    currency = base.normalize_currency(currency_match.group(0), country) if currency_match else base.normalize_currency("", country)
    if not candidates:
        return "", None, currency
    edge_candidates = [item for item in candidates if item[3]]
    if edge_candidates:
        _pos, raw, value, _edge, _currency = sorted(edge_candidates, key=lambda item: item[0])[-1]
        return raw, value, currency
    if require_edge or no_price:
        return "", None, currency
    currency_candidates = [item for item in candidates if item[4]]
    if currency_candidates:
        _pos, raw, value, _edge, _currency = sorted(currency_candidates, key=lambda item: item[0])[-1]
        return raw, value, currency
    _pos, raw, value, _edge, _currency = sorted(candidates, key=lambda item: item[0])[-1]
    return raw, value, currency


def normalize_result(result):
    data = BASE_NORMALIZE_RESULT(result)
    item = result.get("item") or {}
    wine_list = ((item.get("pw") or {}).get("wine_list") or {})
    country = (data.get("venue") or {}).get("country") or ""
    raw_text = item.get("text") or ""
    price_text, price_value, currency = parse_price(raw_text, country, result.get("page"))
    data["priceValue"] = price_value
    data["currency"] = currency
    data["prices"] = [price_text] if price_text else []
    data["wineList"]["externalUrl"] = wine_list.get("external") or ""
    return data


base.parse_price = parse_price
base.normalize_result = normalize_result


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload = base.search(parse_qs(urlparse(self.path).query))
            base.json_response(self, payload)
        except Exception as exc:
            base.json_response(self, {"error": str(exc)}, status=500)
