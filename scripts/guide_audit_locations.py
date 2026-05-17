import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import guide_collect as guide
import guide_discover_wine_lists as discover


ROOT = Path(__file__).resolve().parents[1]


def host(url):
    value = urlparse(url or "").netloc.lower()
    return value[4:] if value.startswith("www.") else value


def distance_km(a_lat, a_lng, b_lat, b_lng):
    try:
        a_lat = math.radians(float(a_lat))
        a_lng = math.radians(float(a_lng))
        b_lat = math.radians(float(b_lat))
        b_lng = math.radians(float(b_lng))
    except (TypeError, ValueError):
        return None
    d_lat = b_lat - a_lat
    d_lng = b_lng - a_lng
    value = math.sin(d_lat / 2) ** 2 + math.cos(a_lat) * math.cos(b_lat) * math.sin(d_lng / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def variant_rows(con, target):
    rows = con.execute(
        """
        select gp.name, gp.city, gp.country, gp.address, gp.website_url, gp.place_url, s.code as source
        from guide_places gp
        join guide_sources s on s.id = gp.source_id
        where gp.normalized_name = ?
        order by
          case when gp.address is not null and gp.address != '' then 0 else 1 end,
          case when lower(coalesce(gp.city, '')) = lower(coalesce(?, '')) then 0 else 1 end,
          s.code
        limit 8
        """,
        (target["normalized_name"], target["city"]),
    ).fetchall()
    variants = [dict(target)]
    for row in rows:
        item = dict(target)
        for key in ["name", "city", "country", "address", "website_url"]:
            if row[key]:
                item[key] = row[key]
        item["guide_source"] = row["source"]
        item["guide_place_url"] = row["place_url"]
        variants.append(item)
    seen = set()
    unique = []
    for item in variants:
        key = "|".join(str(item.get(part) or "") for part in ["name", "city", "country", "address"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def resolve_best(con, target, api_key):
    best = None
    best_variant = None
    last_error = ""
    for variant in variant_rows(con, target):
        resolved = discover.resolve_google_place(variant, api_key)
        if resolved.get("error") and not resolved.get("website_url"):
            last_error = resolved["error"]
            continue
        score = float(resolved.get("score") or 0)
        if resolved.get("website_url"):
            score += 0.25
        if variant.get("address"):
            score += 0.15
        if not best or score > best[0]:
            best = (score, resolved)
            best_variant = variant
    if best:
        return best[1], best_variant
    return {"error": last_error or "Google Places returned no verified restaurant."}, target


def update_target(con, target, resolved):
    old_host = host(target["website_url"])
    new_host = host(resolved.get("website_url"))
    host_changed = bool(old_host and new_host and old_host != new_host)
    moved_km = distance_km(target["lat"], target["lng"], resolved.get("lat"), resolved.get("lng"))
    location_changed = moved_km is not None and moved_km > 10
    changed = host_changed or location_changed

    if changed:
        con.execute("delete from guide_wine_entries where target_id=?", (target["id"],))
        con.execute("delete from wine_list_sources where target_id=?", (target["id"],))

    con.execute(
        """
        update restaurant_targets
        set website_url=coalesce(nullif(?, ''), website_url),
            address=coalesce(nullif(?, ''), address),
            lat=coalesce(?, lat),
            lng=coalesce(?, lng),
            status=case
              when ? then 'not_checked'
              when coalesce(nullif(?, ''), website_url) is null or coalesce(nullif(?, ''), website_url) = '' then 'missing_website'
              else status
            end,
            last_checked_at=case when ? then null else last_checked_at end,
            last_error=case when ? then null else ? end
        where id=?
        """,
        (
            resolved.get("website_url") or "",
            resolved.get("address") or "",
            resolved.get("lat"),
            resolved.get("lng"),
            1 if changed else 0,
            resolved.get("website_url") or "",
            resolved.get("website_url") or "",
            1 if changed else 0,
            1 if changed else 0,
            resolved.get("error") or None,
            target["id"],
        ),
    )
    return changed, moved_km


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-targets", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.12)
    args = parser.parse_args()

    api_key = discover.load_env_key()
    if not api_key:
        raise SystemExit("GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY is required.")

    guide.init_db()
    with guide.connect() as con:
        started_at = guide.now_sql()
        run = con.execute(
            "insert into guide_collection_runs(started_at, status, sources_requested) values(?, 'running', ?)",
            (started_at, "location_audit_google_places"),
        )
        run_id = run.lastrowid
        rows = con.execute(
            """
            select *
            from restaurant_targets
            order by priority desc, name, city
            """
        ).fetchall()
        if args.max_targets > 0:
            rows = rows[: args.max_targets]

        total = len(rows)
        changed = 0
        errors = 0
        for index, row in enumerate(rows, start=1):
            target = dict(row)
            guide.write_progress(
                runId=run_id,
                status="running",
                phase="auditing_locations",
                message="Auditing restaurant address, map pin, and official website with Google Places.",
                currentTarget=target.get("name") or "",
                currentUrl=target.get("website_url") or "",
                targetsCollected=con.execute("select count(*) from restaurant_targets").fetchone()[0],
                processedTargets=index - 1,
                totalWebsites=total,
                websitesChecked=index - 1,
                errors=errors,
                progressPercent=round(((index - 1) / total) * 100, 1) if total else 0,
            )
            try:
                resolved, _variant = resolve_best(con, target, api_key)
                did_change, _distance = update_target(con, target, resolved)
                changed += 1 if did_change else 0
            except Exception as exc:
                errors += 1
                con.execute(
                    "update restaurant_targets set last_error=? where id=?",
                    (str(exc), target["id"]),
                )
            if index % 10 == 0:
                con.commit()
            time.sleep(args.sleep)

        con.execute(
            """
            update guide_collection_runs
            set finished_at=?, status='completed', target_count=?, websites_checked=?,
                errors=?, notes=?
            where id=?
            """,
            (
                guide.now_sql(),
                con.execute("select count(*) from restaurant_targets").fetchone()[0],
                total,
                errors,
                json.dumps({"locationChangedOrWebsiteChanged": changed}, ensure_ascii=False),
                run_id,
            ),
        )
        guide.write_progress(
            runId=run_id,
            status="completed",
            phase="location_audit_completed",
            message="Restaurant address, map pin, and official website audit completed.",
            targetsCollected=con.execute("select count(*) from restaurant_targets").fetchone()[0],
            processedTargets=total,
            totalWebsites=total,
            websitesChecked=total,
            errors=errors,
            progressPercent=100,
        )
        guide.export_status(con, run_id)
        con.commit()
        print(f"audited={total} changed={changed} errors={errors}")


if __name__ == "__main__":
    sys.exit(main())
