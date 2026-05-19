import argparse
import calendar
import json
import os
import re
import sqlite3
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

import guide_collect as guide
import firebase_sync


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA_DIR = ROOT / "public" / "data"
GOOGLE_FIND_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
GOOGLE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
BLOCKED_HOSTS = {
    "facebook.com",
    "instagram.com",
    "tripadvisor.",
    "thefork.",
    "opentable.",
    "ubereats.",
    "doordash.",
    "guide.michelin.com",
    "laliste.com",
    "theworlds50best.com",
}


def load_env_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if key:
        return key.strip()
    for filename in [".env.local", ".env"]:
        path = ROOT / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() in {"GOOGLE_MAPS_API_KEY", "GOOGLE_PLACES_API_KEY"}:
                return value.strip().strip('"').strip("'")
    return ""


def http_json(url, params, timeout=20):
    body, _content_type = guide.fetch_text(f"{url}?{urlencode(params)}", timeout=timeout)
    if not isinstance(body, str):
        raise RuntimeError("Expected JSON response, received binary content")
    return json.loads(body)


def normalized_host(url):
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def valid_website(url):
    host = normalized_host(url)
    return bool(host) and not any(blocked in host for blocked in BLOCKED_HOSTS)


def name_score(left, right):
    left_norm = guide.normalize_name(left)
    right_norm = guide.normalize_name(right)
    if not left_norm or not right_norm:
        return 0
    if left_norm in right_norm or right_norm in left_norm:
        return 1
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def google_query(target):
    name = str(target.get("name") or "").strip()
    address = str(target.get("address") or "").strip()
    city = str(target.get("city") or "").strip()
    country = str(target.get("country") or "").strip()
    if address and address.lower() not in {city.lower(), f"{city}, {country}".lower()}:
        return " ".join(part for part in [name, address, city, country] if part)
    return " ".join(part for part in [name, "restaurant", city, country] if part)


def google_candidates(target):
    name = str(target.get("name") or "").strip()
    address = str(target.get("address") or "").strip()
    city = str(target.get("city") or "").strip()
    country = str(target.get("country") or "").strip()
    queries = [google_query(target)]
    if address:
        queries.append(" ".join(part for part in [name, address] if part))
    queries.append(" ".join(part for part in [name, "restaurant", city, country] if part))
    queries.append(" ".join(part for part in [name, "Michelin restaurant", city, country] if part))
    seen = set()
    return [query for query in queries if query and not (query in seen or seen.add(query))]


def is_food_place(candidate):
    types = set(candidate.get("types") or [])
    if candidate.get("business_status"):
        return True
    food_types = {"restaurant", "food", "bar", "cafe", "meal_takeaway", "meal_delivery", "lodging"}
    return bool(types & food_types)


def charge_google_request(budget, sku):
    if budget is None:
        return
    limit = int(budget.get("limit") or 0)
    if limit and int(budget.get("used") or 0) >= limit:
        raise RuntimeError(f"Google Places request cap reached ({limit}).")
    budget["used"] = int(budget.get("used") or 0) + 1
    budget[sku] = int(budget.get(sku) or 0) + 1


def resolve_google_place(target, api_key, budget=None):
    if not api_key:
        return {"error": "Google Places API key is not configured on this PC."}

    last_error = "Google Places returned no result."
    candidate = None
    score = 0
    for query in google_candidates(target):
        charge_google_request(budget, "findPlace")
        payload = http_json(
            GOOGLE_FIND_URL,
            {
                "input": query,
                "inputtype": "textquery",
                "fields": "place_id,name,formatted_address,geometry,business_status,types",
                "key": api_key,
            },
        )
        status = payload.get("status")
        if status == "ZERO_RESULTS":
            last_error = "Google Places returned no result."
            continue
        if status != "OK":
            return {"error": f"Google Places {status}: {payload.get('error_message') or 'request failed'}"}

        candidates = [item for item in payload.get("candidates") or [] if is_food_place(item)]
        if not candidates:
            last_error = "Google Places found candidates, but none looked like a restaurant."
            continue
        candidates.sort(key=lambda item: name_score(target.get("name", ""), item.get("name", "")), reverse=True)
        candidate = candidates[0]
        score = name_score(target.get("name", ""), candidate.get("name", ""))
        if score >= 0.55:
            break
        last_error = f"Google Places candidate looked different: {candidate.get('name')}"
        candidate = None
    if not candidate:
        return {"error": last_error}

    charge_google_request(budget, "details")
    details = http_json(
        GOOGLE_DETAILS_URL,
        {
            "place_id": candidate["place_id"],
            "fields": "name,formatted_address,geometry,website,url,business_status,types",
            "key": api_key,
        },
    )
    if details.get("status") != "OK":
        return {"error": f"Google Place Details {details.get('status')}: {details.get('error_message') or 'request failed'}"}
    result = details.get("result") or {}
    website = result.get("website") or ""
    maps_url = result.get("url") or ""
    geometry = result.get("geometry") or {}
    location = geometry.get("location") or {}
    if website and not valid_website(website):
        website = ""
    return {
        "website_url": website,
        "google_maps_url": maps_url,
        "address": result.get("formatted_address") or candidate.get("formatted_address") or "",
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "place_name": result.get("name") or candidate.get("name"),
        "score": score,
        "error": "" if website else "Google Places found the place but no official website.",
    }


def update_target_from_google(con, target, resolved):
    con.execute(
        """
        update restaurant_targets
        set website_url=coalesce(nullif(?, ''), website_url),
            address=coalesce(nullif(?, ''), address),
            lat=coalesce(?, lat),
            lng=coalesce(?, lng),
            last_error=case when ? != '' then ? else last_error end
        where id=?
        """,
        (
            resolved.get("website_url") or "",
            resolved.get("address") or "",
            resolved.get("lat"),
            resolved.get("lng"),
            resolved.get("error") or "",
            resolved.get("error") or "",
            target["id"],
        ),
    )


def direct_wine_source(url, html, watches):
    text = guide.html_to_lines(html)
    lines = [line for line in re.split(r"[\r\n]+", text or "") if guide.likely_wine_line(line, watches)]
    if len(lines) >= 2:
        return True
    return bool(re.search(r"\b(?:wine list|winelist|carte des vins|vinkort|wein(?:karte)?|lista de vinos)\b", text, re.I))


def discover_target(con, target, watches, max_links):
    content, content_type = guide.fetch_text(target["website_url"], timeout=6)
    if not isinstance(content, str):
        return 0, 0, "Official website returned binary content."

    links = guide.discover_candidate_wine_links(target["website_url"], content, max_pages=max(2, min(4, max_links)))
    if direct_wine_source(target["website_url"], content, watches):
        links.insert(0, {"url": target["website_url"], "text": "Official website", "score": 1})

    unique = []
    seen = set()
    for link in links:
        parsed = urlparse(link["url"])
        if parsed.scheme not in {"http", "https"}:
            continue
        key = link["url"].split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        unique.append({"url": key, "text": link.get("text", ""), "score": link.get("score", 0)})

    if not unique:
        con.execute(
            "update restaurant_targets set status='no_wine_list', last_checked_at=current_timestamp, last_error=null where id=?",
            (target["id"],),
        )
        return 0, 0, ""

    sources = 0
    lines = 0
    errors = []
    for link in unique[:max_links]:
        found, count, error = guide.scan_wine_source(con, target, link["url"], watches, link.get("score", 0))
        sources += found
        lines += count
        if error:
            errors.append(error)
        if sources and (count >= 10 or link.get("score", 0) >= 120):
            break

    con.execute(
        """
        update restaurant_targets
        set status=?, last_checked_at=current_timestamp, last_error=?
        where id=?
        """,
        ("found" if sources else "review", "; ".join(errors[:3]) if errors else None, target["id"]),
    )
    return sources, lines, "; ".join(errors[:3])


def write_watch_hits(con):
    watches = guide.load_watchlist()
    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    hits = []
    rows = con.execute(
        """
        select e.raw_text, e.vintage, e.price_text, e.price_value, e.currency,
               t.name, t.city, t.country, e.source_url
        from guide_wine_entries e
        join restaurant_targets t on t.id = e.target_id
        order by e.last_seen_at desc
        limit 1000
        """
    ).fetchall()
    for watch in watches:
        if not watch.get("active", True):
            continue
        needle = guide.normalize_name(watch.get("keyword"))
        vintage = str(watch.get("vintage") or "")
        for row in rows:
            text = row["raw_text"] or ""
            if needle not in guide.normalize_name(text):
                continue
            if vintage and vintage not in text and vintage != str(row["vintage"] or ""):
                continue
            hits.append(dict(row))
    (PUBLIC_DATA_DIR / "guide-watch-hits.json").write_text(
        json.dumps(hits[:500], ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return len(hits)


def db_counts(con):
    return {
        "targets": con.execute("select count(1) from restaurant_targets").fetchone()[0],
        "withWebsite": con.execute(
            "select count(1) from restaurant_targets where website_url is not null and length(website_url)>0"
        ).fetchone()[0],
        "wineListSources": con.execute("select count(1) from wine_list_sources").fetchone()[0],
        "wineLines": con.execute("select count(1) from guide_wine_entries").fetchone()[0],
        "review": con.execute("select count(1) from restaurant_targets where status in ('review','error')").fetchone()[0],
    }


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def dashboard_payload(con, progress_payload):
    counts = db_counts(con)
    target_summary = con.execute(
        """
        select
          count(1) as totalTargets,
          sum(case when status != 'not_checked' then 1 else 0 end) as checkedTargets,
          sum(case when status = 'no_wine_list' then 1 else 0 end) as noWineList,
          sum(case when status in ('not_checked','missing_website') then 1 else 0 end) as pending,
          sum(case when status in ('review','error') then 1 else 0 end) as needsReview,
          sum(case when status = 'error' then 1 else 0 end) as errors,
          sum(case when status != 'not_checked' and lat is not null and lng is not null then 1 else 0 end) as mappedTargets
        from restaurant_targets
        """
    ).fetchone()
    source_summary = con.execute(
        """
        select
          count(1) as totalSources,
          count(distinct case when status = 'found' and parser_status = 'parsed' and coalesce(line_count, 0) > 0 then target_id end) as foundWineList,
          sum(case when status = 'found' and parser_status = 'parsed' and coalesce(line_count, 0) > 0 then 1 else 0 end) as parsedSources,
          sum(case when status != 'found' or parser_status != 'parsed' or coalesce(line_count, 0) = 0 then 1 else 0 end) as parseReviewSources,
          sum(case when parser_status = 'parsed' and coalesce(line_count, 0) = 0 then 1 else 0 end) as emptyParsedSources
        from wine_list_sources
        """
    ).fetchone()
    summary = row_to_dict(target_summary)
    summary.update(row_to_dict(source_summary))
    collection_summary = {key: int(value or 0) for key, value in summary.items()}
    map_targets = [
        row_to_dict(row)
        for row in con.execute(
            """
            with source_counts as (
              select target_id,
                     count(1) as source_count,
                     sum(case when status = 'found' and parser_status = 'parsed' and coalesce(line_count, 0) > 0 then 1 else 0 end) as verified_source_count,
                     sum(case when status != 'found' or parser_status != 'parsed' or coalesce(line_count, 0) = 0 then 1 else 0 end) as review_source_count
              from wine_list_sources
              group by target_id
            ),
            entry_counts as (
              select target_id, count(1) as line_count
              from guide_wine_entries
              group by target_id
            ),
            wine_choices as (
              select target_id, url, source_type, status as source_status, parser_status, line_count
              from (
                select
                  s.target_id,
                  s.url,
                  s.source_type,
                  s.status,
                  s.parser_status,
                  s.line_count,
                  row_number() over (
                    partition by s.target_id
                    order by
                      case when s.status = 'found' and s.parser_status = 'parsed' and coalesce(s.line_count, 0) > 0 then 0 else 1 end,
                      case when s.source_type = 'pdf' then 0 else 1 end,
                      coalesce(s.line_count, 0) desc,
                      s.last_checked_at desc,
                      s.discovered_at desc
                  ) as choice_rank
                from wine_list_sources s
              )
              where choice_rank = 1
            )
            select
              t.id,
              t.name,
              t.city,
              t.country,
              t.address,
              t.lat,
              t.lng,
              t.website_url as websiteUrl,
              t.status,
              t.last_checked_at as lastCheckedAt,
              t.last_error as lastError,
              wc.url as wineListUrl,
              wc.source_type as wineListType,
              wc.source_status as wineListStatus,
              wc.parser_status as wineListParserStatus,
              coalesce(wc.line_count, 0) as chosenWineLineCount,
              coalesce(sc.source_count, 0) as wineListCount,
              coalesce(sc.verified_source_count, 0) as verifiedWineListCount,
              coalesce(sc.review_source_count, 0) as reviewSourceCount,
              coalesce(ec.line_count, 0) as wineLineCount
            from restaurant_targets t
            left join source_counts sc on sc.target_id = t.id
            left join entry_counts ec on ec.target_id = t.id
            left join wine_choices wc on wc.target_id = t.id
            where t.status != 'not_checked'
              and t.lat is not null
              and t.lng is not null
            order by t.last_checked_at desc, t.name asc
            limit 7000
            """
        )
    ]
    status_counts = [
        row_to_dict(row)
        for row in con.execute("select status, count(1) as count from restaurant_targets group by status order by count desc")
    ]
    return {
        "generatedAt": progress_payload.get("generatedAt"),
        "progress": progress_payload,
        "counts": counts,
        "statusCounts": status_counts,
        "collectionSummary": collection_summary,
        "mapTargets": map_targets,
    }


def write_live_progress(con, **payload):
    payload["dbCounts"] = db_counts(con)
    guide.write_progress(**payload)
    firebase_sync.publish_progress(dashboard_payload(con, payload))


def sql_time_to_epoch(value):
    if not value:
        return time.time()
    try:
        return calendar.timegm(time.strptime(value.replace("+00:00", ""), "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return time.time()


def timing_payload(started_at, checked=0, total=0, completed=False):
    started_epoch = sql_time_to_epoch(started_at)
    now_epoch = time.time()
    elapsed = max(0, int(now_epoch - started_epoch))
    checked = int(checked or 0)
    total = int(total or 0)
    payload = {
        "startedAt": started_at,
        "elapsedSeconds": elapsed,
        "progressPercent": round((checked / total) * 100, 1) if total else 0,
    }
    if completed:
        payload["finishedAt"] = guide.now_sql()
        payload["durationSeconds"] = elapsed
        payload["estimatedRemainingSeconds"] = 0
        return payload
    if checked > 0 and total > checked and elapsed > 0:
        remaining = int((total - checked) * (elapsed / checked))
        payload["estimatedRemainingSeconds"] = remaining
        payload["estimatedFinishAt"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now_epoch + remaining))
    else:
        payload["estimatedRemainingSeconds"] = None
        payload["estimatedFinishAt"] = ""
    return payload


def export_status(con, run_id, watch_hits=0):
    previous = {}
    status_path = PUBLIC_DATA_DIR / "guide-status.json"
    if status_path.exists():
        try:
            previous = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    guide.export_status(con, run_id)
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    for key in ["sourceStats", "totalStats", "sourceIssues"]:
        if key in previous and key not in payload:
            payload[key] = previous[key]
    payload["lastRun"]["watch_hits"] = watch_hits
    status_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-targets", type=int, default=0, help="0 means all restaurant targets.")
    parser.add_argument("--max-links", type=int, default=5)
    parser.add_argument("--skip-google", action="store_true")
    parser.add_argument("--enable-google-places", action="store_true", help="Allow paid Google Places calls. Off by default.")
    parser.add_argument(
        "--max-google-requests",
        type=int,
        default=int(os.environ.get("WHEREISKELLEY_MAX_GOOGLE_REQUESTS", "200")),
        help="Paid Google Places request cap for this run. 0 means no cap.",
    )
    parser.add_argument("--refresh-websites", action="store_true", help="Resolve Google Places even if website_url already exists.")
    parser.add_argument("--recheck-all", action="store_true", help="Recheck targets that were already found or already had no wine list.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace saved wine-list sources and lines for each checked target.")
    parser.add_argument("--sleep", type=float, default=0.18)
    args = parser.parse_args()

    guide.init_db()
    google_enabled = (
        not args.skip_google
        and (args.enable_google_places or os.environ.get("WHEREISKELLEY_ENABLE_GOOGLE_PLACES") == "1")
    )
    api_key = load_env_key() if google_enabled else ""
    google_budget = {
        "limit": max(0, int(args.max_google_requests or 0)),
        "used": 0,
        "findPlace": 0,
        "details": 0,
    }
    with guide.connect() as con:
        started_at = guide.now_sql()
        run = con.execute(
            "insert into guide_collection_runs(started_at, status, sources_requested) values(?, 'running', ?)",
            (started_at, "existing_targets_google_places_wine_lists"),
        )
        run_id = run.lastrowid
        if google_enabled and not api_key:
            message = (
                "GOOGLE_MAPS_API_KEY is not configured locally. "
                "Add it to .env.local or the current PowerShell session before running full wine-list discovery."
            )
            con.execute(
                "update guide_collection_runs set finished_at=?, status='error', target_count=(select count(*) from restaurant_targets), errors=1, notes=? where id=?",
                (guide.now_sql(), message, run_id),
            )
            write_live_progress(
                con,
                runId=run_id,
                status="error",
                phase="missing_google_key",
                targetsCollected=con.execute("select count(*) from restaurant_targets").fetchone()[0],
                errors=1,
                message=message,
                **timing_payload(started_at, 0, 0, completed=True),
            )
            export_status(con, run_id, 0)
            con.commit()
            raise SystemExit(message)
        watches = guide.load_watchlist()
        if args.recheck_all:
            rows = con.execute(
                """
                select *
                from restaurant_targets
                order by priority desc, last_checked_at is not null, name
                """
            ).fetchall()
        else:
            rows = con.execute(
                """
                select *
                from restaurant_targets
                where coalesce(status, 'not_checked') not in ('found', 'no_wine_list')
                order by priority desc, last_checked_at is not null, name
                """
            ).fetchall()
        if args.max_targets and args.max_targets > 0:
            rows = rows[: args.max_targets]

        targets_total = con.execute("select count(*) from restaurant_targets").fetchone()[0]
        websites_checked = 0
        wine_lists_found = 0
        wine_lines_found = 0
        errors = 0
        google_resolved = 0
        google_missing = 0

        for index, row in enumerate(rows, start=1):
            target = dict(row)
            current_sources = 0
            current_lines = 0
            write_live_progress(
                con,
                runId=run_id,
                phase="resolving_websites",
                currentTarget=target.get("name", ""),
                currentUrl=target.get("website_url") or "",
                targetsCollected=targets_total,
                processedTargets=index - 1,
                websitesChecked=websites_checked,
                totalWebsites=len(rows),
                wineListsFound=wine_lists_found,
                wineLinesFound=wine_lines_found,
                errors=errors,
                message="Resolving official website from Google Places, then checking it for wine lists.",
                **timing_payload(started_at, index - 1, len(rows)),
            )

            needs_google = args.refresh_websites or not target.get("website_url")
            if needs_google and not args.skip_google:
                try:
                    resolved = resolve_google_place(target, api_key, google_budget)
                except RuntimeError as exc:
                    args.skip_google = True
                    resolved = {"error": str(exc)}
                update_target_from_google(con, target, resolved)
                if resolved.get("website_url"):
                    google_resolved += 1
                    target["website_url"] = resolved["website_url"]
                    target["address"] = resolved.get("address") or target.get("address")
                    target["lat"] = resolved.get("lat") or target.get("lat")
                    target["lng"] = resolved.get("lng") or target.get("lng")
                else:
                    google_missing += 1
                time.sleep(args.sleep)

            if not target.get("website_url"):
                if not args.skip_google:
                    con.execute(
                        "update restaurant_targets set status='missing_website', last_checked_at=current_timestamp where id=?",
                        (target["id"],),
                    )
                con.commit()
                write_live_progress(
                    con,
                    runId=run_id,
                    phase="checking_wine_lists",
                    currentTarget=target.get("name", ""),
                    currentUrl="",
                    targetsCollected=targets_total,
                    processedTargets=index,
                    websitesChecked=websites_checked,
                    totalWebsites=len(rows),
                    wineListsFound=wine_lists_found,
                    wineLinesFound=wine_lines_found,
                    errors=errors,
                    message="Restaurant website is missing; moved to review.",
                    **timing_payload(started_at, index, len(rows)),
                )
                continue

            websites_checked += 1
            try:
                if args.replace_existing:
                    con.execute("delete from guide_wine_entries where target_id=?", (target["id"],))
                    con.execute("delete from wine_list_sources where target_id=?", (target["id"],))
                sources, lines, error = discover_target(con, target, watches, args.max_links)
                current_sources = sources
                current_lines = lines
                wine_lists_found += sources
                wine_lines_found += lines
                if error:
                    errors += 1
            except Exception as exc:
                errors += 1
                con.execute(
                    "update restaurant_targets set status='error', last_error=?, last_checked_at=current_timestamp where id=?",
                    (str(exc), target["id"]),
                )

            con.commit()
            write_live_progress(
                con,
                runId=run_id,
                phase="checking_wine_lists",
                currentTarget=target.get("name", ""),
                currentUrl=target.get("website_url") or "",
                targetsCollected=targets_total,
                processedTargets=index,
                websitesChecked=websites_checked,
                totalWebsites=len(rows),
                wineListsFound=wine_lists_found,
                wineLinesFound=wine_lines_found,
                errors=errors,
                message=(
                    "Verified a wine list for this restaurant."
                    if current_sources
                    else "Checked restaurant; wine-list source needs review or was not found."
                ),
                **timing_payload(started_at, index, len(rows)),
            )

        watch_hits = write_watch_hits(con)
        con.execute(
            """
            update guide_collection_runs
            set finished_at=?, status='completed', target_count=?, websites_checked=?,
                wine_lists_found=?, wine_lines_found=?, watch_hits=?, errors=?, notes=?
            where id=?
            """,
            (
                guide.now_sql(),
                targets_total,
                websites_checked,
                wine_lists_found,
                wine_lines_found,
                watch_hits,
                errors,
                json.dumps(
                    {
                        "googleResolved": google_resolved,
                        "googleMissingWebsite": google_missing,
                        "googleEnabled": google_enabled and bool(api_key),
                        "googlePlacesRequests": google_budget,
                        "durationSeconds": timing_payload(started_at, len(rows), len(rows), completed=True)["durationSeconds"],
                    },
                    ensure_ascii=False,
                ),
                run_id,
            ),
        )
        write_live_progress(
            con,
            runId=run_id,
            status="completed",
            phase="completed",
            targetsCollected=targets_total,
            processedTargets=len(rows),
            websitesChecked=websites_checked,
            totalWebsites=len(rows),
            wineListsFound=wine_lists_found,
            wineLinesFound=wine_lines_found,
            errors=errors,
            message="Wine-list discovery completed.",
            **timing_payload(started_at, len(rows), len(rows), completed=True),
        )
        export_status(con, run_id, watch_hits)
        result_payload = {}
        for filename in ["guide-status.json", "guide-watch-hits.json"]:
            path = PUBLIC_DATA_DIR / filename
            if path.exists():
                try:
                    result_payload[filename.removesuffix(".json").replace("-", "_")] = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        result_payload["dbCounts"] = db_counts(con)
        result_payload["completedAt"] = guide.now_sql()
        result_payload.update(dashboard_payload(con, result_payload.get("guide_status", {}).get("lastRun", {}) if isinstance(result_payload.get("guide_status"), dict) else {}))
        firebase_sync.publish_result(result_payload)
        con.commit()
        print(
            f"targets={targets_total} checked={websites_checked} "
            f"google_resolved={google_resolved} wine_lists={wine_lists_found} "
            f"wine_lines={wine_lines_found} watch_hits={watch_hits} errors={errors}"
        )


if __name__ == "__main__":
    main()
