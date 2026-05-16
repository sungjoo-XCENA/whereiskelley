# Star Wine Local Search

Personal local search app for Star Wine List wine-list files.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\run-server.ps1
```

Open `http://localhost:4317`.

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

The Vercel version does not persist SQLite/PDF data yet. It searches the public Star Wine List search API live and returns the same result shape as the local UI. Persistent cloud storage should move to Turso/libSQL plus Vercel Blob later.

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
