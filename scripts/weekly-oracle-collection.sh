#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${WHEREISKELLEY_APP_DIR:-/home/opc/whereiskelley}"
PYTHON_BIN="${WHEREISKELLEY_PYTHON:-python3}"
LOCK_FILE="${WHEREISKELLEY_COLLECTION_LOCK:-/tmp/whereiskelley-collection.lock}"
STATE_DIR="${WHEREISKELLEY_COLLECTION_STATE_DIR:-/home/opc/.local/state/whereiskelley}"
LAST_START_FILE="$STATE_DIR/last-scheduled-collection-start"
MIN_INTERVAL_SECONDS=$((14 * 24 * 60 * 60))

cd "$APP_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "A scheduled collection already owns the collection lock; skipping."
  exit 0
fi

if pgrep -f '[g]uide_discover_wine_lists.py' >/dev/null; then
  echo "A dashboard or manual collection is already running; skipping."
  exit 0
fi

mkdir -p "$STATE_DIR"
now_epoch="$(date +%s)"
if [[ -f "$LAST_START_FILE" ]]; then
  last_epoch="$(cat "$LAST_START_FILE" 2>/dev/null || echo 0)"
  if [[ "$last_epoch" =~ ^[0-9]+$ ]] && (( now_epoch - last_epoch < MIN_INTERVAL_SECONDS )); then
    echo "The last scheduled collection started less than 14 days ago; skipping this Monday."
    exit 0
  fi
fi
printf '%s\n' "$now_epoch" > "$LAST_START_FILE"

exec "$PYTHON_BIN" scripts/run_published_wine_collection.py \
  --max-links "${WHEREISKELLEY_DISCOVERY_MAX_LINKS:-60}" \
  --workers "${WHEREISKELLEY_DISCOVERY_WORKERS:-24}" \
  --source-workers "${WHEREISKELLEY_SOURCE_WORKERS:-12}" \
  --pdf-workers "${WHEREISKELLEY_PDF_WORKERS:-$(python3 -c 'import os; print(max(1, round((os.cpu_count() or 2) * 0.8)))')}" \
  --sleep "${WHEREISKELLEY_DISCOVERY_SLEEP:-0.08}"
