import json
import re
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
    item = result.get("item") or {}
    city_obj = result.get("city") or {}
    region = item.get("region") or {}
    slug = city_obj.get("slug") or (slugify(city) if city and city != country else "") or region.get("slug") or slugify(city)
    location = fetch_location(slug)
    lat = location.get("lat") if location else None
    lng = location.get("lng") if location else None
    star_map_url = ((location or {}).get("urls") or {}).get("map")
    if lat is None or lng is None:
        lat, lng = COUNTRY_COORDS.get(country, (None, None))
    return slug, lat, lng, star_map_url or ""


def parse_price(line):
    def to_value(raw):
        compact = re.sub(r"\s+", "", raw)
        if re.fullmatch(r"\d+[,.]\d{2}", compact):
            return float(compact.replace(",", "."))
        compact = re.sub(r"[,.]", "", compact)
        return float(compact)

    text = re.sub(r"\b(19|20)\d{2}\b", " ", line or "")
    candidates = []
    for raw in re.findall(r"\b\d[\d\s.,]*\d\b", text):
        try:
            value = to_value(raw)
        except ValueError:
            continue
        if value >= 10:
            candidates.append((raw.strip(), value))
    raw, value = candidates[-1] if candidates else ("", None)
    currency_match = re.search(r"€|\$|£|¥|₩|CHF|DKK|SEK|NOK|USD|EUR|GBP|CAD|AUD|SGD|HKD|AED", line or "", re.I)
    return raw, value, currency_match.group(0) if currency_match else None


def normalize_result(result):
    item = result.get("item") or {}
    venue = ((item.get("pw") or {}).get("venue") or {})
    wine_list = ((item.get("pw") or {}).get("wine_list") or {})
    raw_text = item.get("text") or ""
    country, city = country_city_from_result(result)
    region_slug, lat, lng, star_map_url = location_from_result(result, country, city)
    price_text, price_value, currency = parse_price(raw_text)
    vintage_match = re.search(r"\b(19|20)\d{2}\b", raw_text)
    venue_url = venue.get("URL") or ""
    venue_id = venue_slug_from_url(venue_url)
    wine_list_id = str(wine_list.get("id") or f"{venue_id}-{result.get('item_id') or ''}")
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


def numeric_price(result):
    value = result.get("priceValue")
    return value if isinstance(value, (int, float)) and value > 0 else 10**18


def search(params):
    query = (params.get("q", [""])[0] or "").strip()
    country = (params.get("country", [""])[0] or "").strip()
    city = (params.get("city", [""])[0] or "").strip().lower()
    vintage = (params.get("vintage", [""])[0] or "").strip()
    limit = min(int(params.get("limit", ["500"])[0] or 500), 2000)
    page_cap = max(1, min(int(params.get("livePageCap", ["10"])[0] or 10), 10))
    if not query:
        return {"query": query, "count": 0, "results": [], "liveRefresh": None}

    results = []
    source_ids = []
    pdf_urls = set()
    entries = 0
    last_page = 1
    for page in range(1, page_cap + 1):
        payload = fetch_json(f"{API_URL}?{urlencode({'t': 'wine-list', 'page': page, 's': query})}")
        lines = [item for item in payload.get("data") or [] if item.get("item_type") == "wine_list_line"]
        entries += len(lines)
        for line in lines:
            if line.get("item_id"):
                source_ids.append(str(line.get("item_id")))
            normalized = normalize_result(line)
            if normalized["wineList"]["fileUrl"]:
                pdf_urls.add(normalized["wineList"]["fileUrl"])
            results.append(normalized)
        meta = payload.get("meta") or {}
        last_page = int(meta.get("last_page") or page)
        if page >= last_page:
            break

    if country:
        results = [item for item in results if item["venue"]["country"] == country]
    if city:
        results = [item for item in results if city in (item["venue"].get("city") or "").lower()]
    if vintage:
        results = [item for item in results if item.get("vintage") == vintage]
    results.sort(key=lambda item: (numeric_price(item), item["venue"].get("name") or ""))
    results = results[:limit]
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "liveRefresh": {
            "query": query,
            "pages": page_cap,
            "lastPage": last_page,
            "complete": page_cap >= last_page,
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
