import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


API_URL = "https://starwinelist.com/api/search"
LOCATION_API_URL = "https://starwinelist.com/api/location/search"
LOCATION_CACHE = {}
COUNTRY_COORDS = {
    "Argentina": (-38.4161, -63.6167),
    "Australia": (-25.2744, 133.7751),
    "Austria": (47.5162, 14.5501),
    "Belgium": (50.5039, 4.4699),
    "Czech Republic": (49.8175, 15.4730),
    "Denmark": (56.2639, 9.5018),
    "France": (46.2276, 2.2137),
    "Germany": (51.1657, 10.4515),
    "Greater China": (35.8617, 104.1954),
    "Hong Kong": (22.3193, 114.1694),
    "Italy": (41.8719, 12.5674),
    "Netherlands": (52.1326, 5.2913),
    "Norway": (60.4720, 8.4689),
    "Singapore": (1.3521, 103.8198),
    "Spain": (40.4637, -3.7492),
    "Sweden": (60.1282, 18.6435),
    "UK": (55.3781, -3.4360),
    "USA": (37.0902, -95.7129),
}
CURRENCY_RE = r"\u20ac|\$|\u00a3|\u00a5|\u20a9|CHF|DKK|SEK|NOK|USD|EUR|GBP|CAD|AUD|SGD|HKD|AED|CNY|CZK|ARS|JPY|KRW"
PRICE_CURRENCY_RE = r"A\$|AU\$|CA\$|HK\$|S\$|US\$|" + CURRENCY_RE
NO_PRICE_RE = r"\b(?:ask\s+(?:your\s+)?sommelier|ask\s+(?:us|staff)|on\s+request|upon\s+request|price\s+on\s+request|market\s+price|enquire|inquire|poa|n/?a|sold\s+out)\b|\ubb38\uc758|\uc2dc\uac00|\uc2ef\uac00"
CURRENCY_ALIASES = {
    "\u20ac": "EUR",
    "$": "USD",
    "\u00a3": "GBP",
    "\u00a5": "JPY",
    "\u20a9": "KRW",
}
COUNTRY_CURRENCIES = {
    "Argentina": "ARS",
    "Australia": "AUD",
    "Austria": "EUR",
    "Belgium": "EUR",
    "Canada": "CAD",
    "Czech Republic": "CZK",
    "Denmark": "DKK",
    "France": "EUR",
    "Germany": "EUR",
    "Greater China": "CNY",
    "Hong Kong": "HKD",
    "Italy": "EUR",
    "Netherlands": "EUR",
    "Norway": "NOK",
    "Singapore": "SGD",
    "Spain": "EUR",
    "Sweden": "SEK",
    "Switzerland": "CHF",
    "UK": "GBP",
    "USA": "USD",
}


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def slugify(value):
    value = (value or "unknown").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def venue_slug_from_url(url):
    try:
        return urlparse(url).path.rstrip("/").split("/")[-1] or "unknown"
    except Exception:
        return "unknown"


def fetch_json(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://starwinelist.com/search",
    }
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_location(slug):
    if not slug:
        return None
    if slug in LOCATION_CACHE:
        return LOCATION_CACHE[slug]
    try:
        payload = fetch_json(f"{LOCATION_API_URL}?{urlencode({'slug': slug})}")
        location = payload.get("data")
    except Exception:
        location = None
    LOCATION_CACHE[slug] = location
    return location


def location_slug_from_result(result, country, city):
    item = result.get("item") or {}
    city_obj = result.get("city") or {}
    region = item.get("region") or {}
    return city_obj.get("slug") or (slugify(city) if city and city != country else "") or region.get("slug") or slugify(city)


def fetch_search_page(query, page):
    payload = fetch_json(f"{API_URL}?{urlencode({'t': 'wine-list', 'page': page, 's': query})}")
    lines = [item for item in payload.get("data") or [] if item.get("item_type") == "wine_list_line"]
    meta = payload.get("meta") or {}
    last_page = int(meta.get("last_page") or page)
    return page, lines, last_page


def country_city_from_result(result):
    item = result.get("item") or {}
    venue = ((item.get("pw") or {}).get("venue") or {})
    city = (result.get("city") or {}).get("name") or (item.get("region") or {}).get("name") or ""
    location = venue.get("location") or result.get("region_breadcrumbs") or ""
    parts = [part.strip() for part in location.split(",") if part.strip()]
    country = parts[-1] if parts else ""
    if parts and (not city or city == country):
        city = parts[0]
    if not country and city:
        country = city
    return country or "Unknown", city


def location_from_result(result, country, city):
    slug = location_slug_from_result(result, country, city)
    location = fetch_location(slug)
    lat = location.get("lat") if location else None
    lng = location.get("lng") if location else None
    star_map_url = ((location or {}).get("urls") or {}).get("map")
    if lat is None or lng is None:
        lat, lng = COUNTRY_COORDS.get(country, (None, None))
    return slug, lat, lng, star_map_url or ""


def normalize_currency(raw, country=""):
    token = (raw or "").strip()
    if not token:
        return COUNTRY_CURRENCIES.get(country)
    upper = token.upper()
    if upper in {"A$", "AU$", "AUD$"}:
        return "AUD"
    if upper in {"CA$", "CAD$"}:
        return "CAD"
    if upper in {"HK$", "HKD$"}:
        return "HKD"
    if upper in {"S$", "SGD$"}:
        return "SGD"
    if upper in {"US$", "USD$"}:
        return "USD"
    return CURRENCY_ALIASES.get(token, token.upper())


def parse_price_number(raw):
    compact = re.sub(r"\s+", "", raw or "")
    compact = re.sub(r"(?<=\d)[oO](?=[,.])", "", compact)
    compact = re.sub(r"(?<=[,.])[oO]", "0", compact)
    compact = re.sub(r"(?<=\d)[oO](?=\d)", "0", compact)
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{2})?", compact):
        return float(compact.replace(",", ""))
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?", compact):
        return float(compact.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+[,.]\d{2}", compact):
        return float(compact.replace(",", "."))
    return float(re.sub(r"[,.]", "", compact))


def display_price(value):
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def strip_search_page_suffix(line, page_number=None):
    text = line or ""
    if page_number:
        text = re.sub(rf"[,;]\s*{re.escape(str(page_number))}\s*$", " ", text)
        text = re.sub(rf"\b(?:page|p\.?)\s*{re.escape(str(page_number))}\s*$", " ", text, flags=re.I)
    return text


def parse_price(line, country="", page_number=None, require_edge=False):
    cleaned = strip_search_page_suffix(line, page_number)
    no_price = re.search(NO_PRICE_RE, cleaned, re.I) is not None
    text = re.sub(r"\b(19|20)\d{2}\b", " ", cleaned)
    text = re.sub(r"\b(?:page|p\.?)\s*\d{1,4}\b", " ", text, flags=re.I)
    text = re.sub(r"\b0\s*[,\.]\s*(?:187|375|5|50|70|75|750|150|1500)\s*(?:l|lt|liter|litre)?\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:37\.?5|75|187|375|500|750|1500)\s*(?:ml|cl)\b", " ", text, flags=re.I)
    patterns = [
        r"(?<![\w])(?:A\$|AU\$|CA\$|HK\$|S\$|US\$)\s*\d{2,6}(?:\s*[,\.]\s*[oO0]{2})?(?![\w])",
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
            try:
                value = parse_price_number(raw_number)
            except ValueError:
                continue
            if value >= 10:
                tail = re.sub(r"[\s,.;:)\]]+$", "", text[match.end():])
                right_edge = not tail
                has_currency = re.search(PRICE_CURRENCY_RE, text[max(0, match.start() - 8):match.end() + 8], re.I) is not None
                candidates.append((match.start(), display_price(value), value, right_edge, has_currency))
                used_spans.append(match.span())
    currency_match = re.search(PRICE_CURRENCY_RE, cleaned, re.I)
    currency = normalize_currency(currency_match.group(0), country) if currency_match else normalize_currency("", country)
    if not candidates:
        return "", None, currency
    edge_candidates = [item for item in candidates if item[3]]
    if edge_candidates:
        _pos, raw, value, _edge, _currency = sorted(edge_candidates, key=lambda item: item[0])[-1]
        return raw, value, currency
    if require_edge:
        return "", None, currency
    if no_price:
        return "", None, currency
    currency_candidates = [item for item in candidates if item[4]]
    if currency_candidates:
        _pos, raw, value, _edge, _currency = sorted(currency_candidates, key=lambda item: item[0])[-1]
        return raw, value, currency
    _pos, raw, value, _edge, _currency = sorted(candidates, key=lambda item: item[0])[-1]
    return raw, value, currency


def normalize_result(result):
    item = result.get("item") or {}
    venue = ((item.get("pw") or {}).get("venue") or {})
    wine_list = ((item.get("pw") or {}).get("wine_list") or {})
    raw_text = item.get("text") or ""
    country, city = country_city_from_result(result)
    region_slug, lat, lng, star_map_url = location_from_result(result, country, city)
    vintage_match = re.search(r"\b(19|20)\d{2}\b", raw_text)
    venue_url = venue.get("URL") or ""
    venue_id = venue_slug_from_url(venue_url)
    wine_list_id = str(wine_list.get("id") or f"{venue_id}-{result.get('item_id') or ''}")
    price_text, price_value, currency = parse_price(raw_text, country, result.get("page"))
    return {
        "id": str(result.get("item_id") or f"{wine_list_id}-{raw_text}"),
        "text": raw_text,
        "producer": None,
        "wineName": None,
        "vintage": vintage_match.group(0) if vintage_match else None,
        "region": (item.get("region") or {}).get("name"),
        "grape": None,
        "priceValue": price_value,
        "currency": currency,
        "prices": [price_text] if price_text else [],
        "section": "Star Wine List search API",
        "pageNumber": result.get("page"),
        "venue": {
            "id": venue_id,
            "name": venue.get("name") or venue_id,
            "type": venue.get("type"),
            "city": city,
            "country": country,
            "regionSlug": region_slug,
            "lat": lat,
            "lng": lng,
            "address": venue.get("location") or "",
            "googleMapsUrl": "",
            "starWineMapUrl": star_map_url,
            "url": venue_url,
        },
        "wineList": {
            "id": wine_list_id,
            "label": f"Wine list {wine_list_id}",
            "downloadUrl": wine_list.get("download_url") or wine_list.get("file") or "",
            "fileUrl": wine_list.get("file") or "",
            "fileViewUrl": wine_list.get("file_view") or "",
            "localFilePath": "",
            "localFileUrl": "",
            "updatedText": wine_list.get("date") or "",
            "updatedDate": wine_list.get("date") or "",
        },
    }


def passes_filters(result, country="", city="", vintage=""):
    raw_text = ((result.get("item") or {}).get("text") or "")
    if vintage and not re.search(rf"\b{re.escape(vintage)}\b", raw_text):
        return False
    if not country and not city:
        return True
    result_country, result_city = country_city_from_result(result)
    if country and result_country != country:
        return False
    if city and city not in (result_city or "").lower():
        return False
    return True


def numeric_price(result):
    value = result.get("priceValue")
    return value if isinstance(value, (int, float)) and value > 0 else 10**18


def search(params):
    query = (params.get("q", [""])[0] or "").strip()
    country = (params.get("country", [""])[0] or "").strip()
    city = (params.get("city", [""])[0] or "").strip().lower()
    vintage = (params.get("vintage", [""])[0] or "").strip()
    limit = min(int(params.get("limit", ["500"])[0] or 500), 5000)
    page_cap = max(1, min(int(params.get("livePageCap", ["200"])[0] or 200), 300))
    if not query:
        return {"query": query, "count": 0, "results": [], "liveRefresh": None}
    upstream_query = query
    if vintage and not re.search(rf"\b{re.escape(vintage)}\b", query):
        upstream_query = f"{query} {vintage}"

    first_page, first_lines, last_page = fetch_search_page(upstream_query, 1)
    target_page = min(page_cap, last_page)
    pages = {first_page: first_lines}
    if target_page > 1:
        workers = min(10, target_page - 1)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch_search_page, upstream_query, page) for page in range(2, target_page + 1)]
            for future in as_completed(futures):
                page, lines, seen_last_page = future.result()
                pages[page] = lines
                last_page = max(last_page, seen_last_page)

    results = []
    source_ids = []
    pdf_urls = set()
    entries = 0
    filtered_lines = []
    for page in sorted(pages):
        lines = pages[page]
        entries += len(lines)
        for line in lines:
            if line.get("item_id"):
                source_ids.append(str(line.get("item_id")))
            if not passes_filters(line, country, city, vintage):
                continue
            filtered_lines.append(line)

    slugs = set()
    for line in filtered_lines:
        line_country, line_city = country_city_from_result(line)
        slug = location_slug_from_result(line, line_country, line_city)
        if slug and slug not in LOCATION_CACHE:
            slugs.add(slug)
    if slugs:
        with ThreadPoolExecutor(max_workers=min(10, len(slugs))) as executor:
            futures = [executor.submit(fetch_location, slug) for slug in slugs]
            for future in as_completed(futures):
                future.result()

    for line in filtered_lines:
        normalized = normalize_result(line)
        if normalized["wineList"]["fileUrl"]:
            pdf_urls.add(normalized["wineList"]["fileUrl"])
        results.append(normalized)

    results.sort(key=lambda item: (numeric_price(item), item["venue"].get("name") or ""))
    results = results[:limit]
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "liveRefresh": {
            "query": query,
            "pages": target_page,
            "lastPage": last_page,
            "complete": target_page >= last_page,
            "pageCap": page_cap,
            "entries": entries,
            "pdfs": len(pdf_urls),
            "sourceItemIds": list(dict.fromkeys(source_ids)),
        },
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload = search(parse_qs(urlparse(self.path).query))
            json_response(self, payload)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, status=500)
