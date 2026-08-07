#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${WHEREISKELLEY_APP_DIR:-/home/opc/whereiskelley}"
PYTHON_BIN="${WHEREISKELLEY_PYTHON:-python3}"
LOCK_FILE="${WHEREISKELLEY_COLLECTION_LOCK:-/tmp/whereiskelley-collection.lock}"

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

exec "$PYTHON_BIN" scripts/guide_discover_wine_lists.py \
  --skip-google \
  --only-with-website \
  --recheck-all \
  --replace-existing \
  --max-links "${WHEREISKELLEY_DISCOVERY_MAX_LINKS:-12}" \
  --sleep "${WHEREISKELLEY_DISCOVERY_SLEEP:-0.08}"
