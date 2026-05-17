# Star Wine Local Search

Personal local search app for Star Wine List wine-list files.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\run-server.ps1
```

Open `http://localhost:4317`.

To use this PC as the collection monitor/server, keep the local server running while collection runs:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-server.ps1
```

For LAN access from another device on the same network:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-server.ps1 -Public
```

The local Dashboard reads live collection state from `/api/guide-collection`, which reads SQLite and `public/data/guide-progress.json` directly. This does not require GitHub or Vercel.

## Guide collection and watchlist

The collector now follows this flow:

1. Read restaurant candidates from Michelin, La Liste, and World's 50 Best.
2. Save those restaurants into `db/starwine.sqlite`.
3. Open each restaurant website when available.
4. Find candidate wine-list pages or PDFs.
5. Save parsed wine lines into the DB.
6. Export a read-only snapshot into `public/data/` so the web search and Dashboard can show it.

Run a small smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect-guides.ps1 -Quick -Discover
```

`-Quick` is only for local smoke testing. It checks a tiny sample and does not overwrite the public `public/data/` snapshot unless `-Snapshot` is also passed.

Run the guide master-list collector:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect-guides.ps1
```

Use this as the yearly restaurant-candidate refresh. The guide restaurant list changes slowly, so it is meant to be run only when Michelin, La Liste, or World's 50 Best publish a meaningful update. For guide collection, `MaxSourceItems=0` and `MaxTargets=0` mean no artificial limit.

Run the website/wine-list discovery stage separately:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect-guides.ps1 -Discover
```

Use this to resume wine-list discovery. It reuses the saved restaurant candidates, skips restaurants already marked `found` or `no_wine_list`, resolves missing official websites through Google Places, then checks official restaurant websites for wine-list pages or PDFs.

For a weekly full refresh, recheck every saved restaurant:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect-guides.ps1 -Discover -RecheckAll
```

Local discovery needs a Google key with `Places API` enabled because the weekly job needs official restaurant websites, not just map pins:

```powershell
$env:GOOGLE_MAPS_API_KEY="your_google_maps_key"
powershell -ExecutionPolicy Bypass -File .\scripts\collect-guides.ps1 -Discover
```

You can also save the key in `.env.local`:

```text
GOOGLE_MAPS_API_KEY=your_google_maps_key
```

For remote monitoring after the local PC stops, set Firebase Realtime Database env vars locally and in Vercel:

```text
FIREBASE_DATABASE_URL=https://your-project-default-rtdb.firebaseio.com
FIREBASE_COLLECTION_PATH=whereiskelley/guideCollection
FIREBASE_AUTH_TOKEN=optional_database_secret_or_id_token
```

During collection the local collector writes live progress to Firebase when `FIREBASE_DATABASE_URL` is set. When collection finishes it writes the DB summary and watched-wine matches there. Vercel reads the same `/api/guide-collection` route, but that route reads Firebase instead of local SQLite.

The annual candidate refresh and the weekly wine-list refresh are intentionally separate:

- annual: `collect-guides.ps1` refreshes Michelin, La Liste, and World's 50 Best restaurant candidates.
- resume: `collect-guides.ps1 -Discover` continues only unfinished or review/error targets.
- weekly: `collect-guides.ps1 -Discover -RecheckAll` uses the saved candidates, finds/updates official websites, scans wine-list HTML/PDF sources, and updates watchlist hits.

Current collection is intentionally target-first:

- `collect-guides.ps1` collects and deduplicates restaurant targets only.
- `collect-guides.ps1 -Discover` is the later website/wine-list discovery stage.
- MICHELIN uses the rendered `https://guide.michelin.com/kr/ko/restaurants/all-starred/page/N` pages through a local browser because plain HTTP requests return an empty challenge response.
- If a guide source is blocked or renders no parseable restaurant cards, the Dashboard shows it under `Source notes` instead of silently pretending it worked.
- Dashboard progress separates `reviewed`, source-level unique restaurants, and merged unique restaurants after cross-source dedupe.

Install the weekly Windows task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-weekly-task.ps1
```

The Dashboard shows:

- DB collection result from the latest exported guide run
- current background collection status when a local run is active
- restaurants saved from the three guide sources
- wine-list pages or PDFs found from official restaurant websites
- watchlist hits from saved guide data and from the current search

During collection, this file is updated continuously:

```powershell
Get-Content .\public\data\guide-progress.json
```

It shows the current phase, current restaurant or wine-list URL, checked websites, found wine lists, parsed wine lines, and errors.
For wine-list discovery runs it also records `startedAt`, `elapsedSeconds`, `processedTargets`, `progressPercent`, `estimatedRemainingSeconds`, and `estimatedFinishAt`. When a run completes, the final snapshot keeps the run's `started_at` and `finished_at`, so the Dashboard can show the total duration.

Watchlist keywords live in:

```text
public/data/watchlist.json
```

Edit that file, then run `collect-guides.ps1 -Discover` again. The generated `public/data/guide-watch-hits.json` feeds the Dashboard alert area.

The web search merges both sources in one result list:

- `Guide DB`: result came from the collected guide restaurant DB.
- `DB`: result came from the exported Star Wine snapshot.
- `Live`: result came from the live Star Wine List API.
- `DB + Live`: the same result was found in more than one source.

## Star Wine search

Star Wine List is not fully crawled. The app uses the live Star Wine search API when you search, then merges those live results with the collected Guide DB snapshot.

This keeps the heavy weekly DB collection focused on restaurants from Michelin, La Liste, and World's 50 Best. Star Wine results are only stored when they are part of a user search/export flow.

## Manual PDF import

If a source blocks automated PDF downloads, open the venue/source link in your normal browser and save the PDF into:

```text
data/manual
```

Name the file with the Star Wine List list id from the download URL. For example:

```text
8845.pdf
```

Then import it:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\import-pdf.ps1
```

The app will attach the PDF to the matching wine list, expose it through the `Local PDF` button, extract searchable text where possible, and keep unparsed PDFs in `Needs review`.

## Notes

- The scraper is deliberately rate-limited. Use `--delay-ms=1500` or higher if you want it gentler.
- PDF text extraction uses the bundled Codex Python runtime when available, then falls back to `python` if it exists on PATH.
- Some wine lists are scanned images. Those files are saved, but may need OCR support later for searchable text.

## Vercel deployment

This repo includes a lightweight Vercel version:

- static UI from `public/`
- serverless live search at `api/search.py`
- Google Maps config at `api/config.js`
- static DB snapshot files from `public/data/`

The Vercel version merges two sources in the same search results:

- exported Guide DB snapshot from `public/data/wine-lines-*.json`
- live Star Wine List API results from `api/search.py`

The production site does not write to SQLite. The local PC owns collection and parsing, then exports the read-only snapshot into `public/data/` and pushes it to GitHub for Vercel to serve.

External guide collection uses these generic tables:

- `guide_sources`: `michelin`, `worlds50best`, `laliste`
- `guide_places`: source-specific restaurant metadata and URLs
- `restaurant_targets`: deduplicated restaurants to check
- `wine_list_sources`: official restaurant wine-list pages or PDFs found by the collector
- `guide_wine_entries`: parsed wine rows from those official lists
- `guide_collection_runs`: collection run history for the Dashboard

Keyword monitoring is stored in:

- `wine_keyword_watches`: registered wine keywords and optional filters
- `wine_keyword_hits`: detected matches from parsed wine-list entries
- `notification_events`: pending/sent alert summaries for email, dashboard cards, or webhook delivery

The weekly local flow is:

1. Reuse saved guide restaurant targets.
2. Resolve missing official websites with Google Places.
3. Visit official restaurant websites.
4. Save wine-list HTML/PDF sources when discovered.
5. Run active keyword watches.
6. Export `public/data/guide-*.json` and the search snapshot for the web app.

Set this environment variable in Vercel Project Settings:

```text
GOOGLE_MAPS_API_KEY=your_google_maps_browser_key
```

Restrict the Google key to:

```text
http://localhost:4317/*
http://127.0.0.1:4317/*
https://your-vercel-project.vercel.app/*
```

and restrict it to the `Maps JavaScript API`.
