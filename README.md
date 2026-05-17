# Star Wine Local Search

Personal local search app for Star Wine List wine-list files.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\run-server.ps1
```

Open `http://localhost:4317`.

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

Run the normal collector:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect-guides.ps1 -Discover -MaxSourceItems 1000 -MaxTargets 1000
```

Install the weekly Windows task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-weekly-task.ps1
```

The Dashboard shows:

- collection status from the latest guide run
- restaurants being tracked from the three guide sources
- wine-list pages or PDFs found from official restaurant websites
- watchlist hits from saved guide data and from the current search

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

## Download and index data

Small smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync.ps1 --countries=germany --limit-venues=5
```

Full sync:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync.ps1
```

Search API sync with direct source PDFs:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-search-api.ps1 --pages=10 --download-pdfs --max-pdfs=20
```

Broad search sweep with direct PDFs:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-search-sweep.ps1 --download-pdfs --max-pdfs=999999
```

The sweep queries digits and letters, deduplicates by Star Wine List `item_id`, and saves progress to `data/search-sweep-state.json`.

Full resumable API sweep:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-full-api-sync.ps1
```

Weekly refresh on Windows Task Scheduler:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-weekly-task.ps1
```

The sync stores metadata and searchable entries in `db/starwine.sqlite`, with downloaded wine lists and extracted text under `data/`.

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

- exported local DB snapshot from `public/data/wine-lines-*.json`
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

1. Refresh external restaurant guides.
2. Deduplicate them into restaurant targets.
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
