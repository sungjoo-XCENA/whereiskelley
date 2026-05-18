import json
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "starwine.sqlite"
PROGRESS_PATH = ROOT / "public" / "data" / "guide-progress.json"


def now_sql():
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


with sqlite3.connect(DB_PATH) as con:
    con.execute("pragma foreign_keys=on")
    con.execute("delete from guide_wine_entries")
    con.execute("delete from wine_list_sources")
    con.execute("delete from guide_collection_runs")
    con.execute(
        """
        update restaurant_targets
        set status='not_checked',
            last_checked_at=null,
            last_error=null
        """
    )
    con.commit()
    total = con.execute("select count(*) from restaurant_targets").fetchone()[0]
    mapped = con.execute(
        "select count(*) from restaurant_targets where lat is not null and lng is not null"
    ).fetchone()[0]

payload = {
    "generatedAt": now_sql(),
    "status": "ready",
    "phase": "ready",
    "message": "Wine-list collection reset. Restaurant targets are preserved.",
    "runId": None,
    "source": "",
    "currentTarget": "",
    "currentUrl": "",
    "targetsCollected": total,
    "processedTargets": 0,
    "websitesChecked": 0,
    "totalWebsites": total,
    "wineListsFound": 0,
    "wineLinesFound": 0,
    "errors": 0,
    "startedAt": "",
    "finishedAt": "",
    "elapsedSeconds": None,
    "estimatedRemainingSeconds": None,
    "estimatedFinishAt": "",
    "durationSeconds": None,
    "progressPercent": 0,
    "dbCounts": {
        "targets": total,
        "withWebsite": 0,
        "wineListSources": 0,
        "wineLines": 0,
        "review": 0,
        "mapped": mapped,
    },
}
PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
print(json.dumps({"targets": total, "mapped": mapped, "wineListSources": 0, "wineLines": 0}, ensure_ascii=False))
