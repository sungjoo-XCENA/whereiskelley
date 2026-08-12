#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${WHEREISKELLEY_APP_DIR:-/home/opc/whereiskelley}"
PYTHON_BIN="${WHEREISKELLEY_PYTHON:-python3}"
LOCK_FILE="${WHEREISKELLEY_SHOP_LOCK:-/tmp/whereiskelley-shop-inventory.lock}"
STATE_DIR="${WHEREISKELLEY_COLLECTION_STATE_DIR:-/home/opc/.local/state/whereiskelley}"
LAST_START_FILE="$STATE_DIR/last-shop-inventory-start"
MIN_INTERVAL_SECONDS=$((14 * 24 * 60 * 60))

cd "$APP_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "A wine-shop inventory refresh is already running; skipping."
  exit 0
fi
if pgrep -f '[w]ine_shop_collect.py inventory' >/dev/null; then
  echo "A dashboard or manual wine-shop inventory refresh is already running; skipping."
  exit 0
fi

mkdir -p "$STATE_DIR"
now_epoch="$(date +%s)"
if [[ -f "$LAST_START_FILE" ]]; then
  last_epoch="$(cat "$LAST_START_FILE" 2>/dev/null || echo 0)"
  if [[ "$last_epoch" =~ ^[0-9]+$ ]] && (( now_epoch - last_epoch < MIN_INTERVAL_SECONDS )); then
    echo "The last wine-shop inventory refresh started less than 14 days ago; skipping."
    exit 0
  fi
fi

if "$PYTHON_BIN" scripts/wine_shop_collect.py inventory \
    --workers "${WHEREISKELLEY_SHOP_INVENTORY_WORKERS:-64}" \
    --per-domain "${WHEREISKELLEY_SHOP_PER_DOMAIN:-2}" \
    --max-pages "${WHEREISKELLEY_SHOP_MAX_PAGES:-160}" \
    --depth "${WHEREISKELLEY_SHOP_MAX_DEPTH:-5}" \
    --stale-days 14 \
    --resume; then
  printf '%s\n' "$(date +%s)" > "$LAST_START_FILE"
  exit 0
fi

echo "Wine-shop inventory refresh failed; leaving the timestamp unchanged for retry."
exit 1
