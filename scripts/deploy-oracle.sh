#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${WHEREISKELLEY_APP_DIR:-/home/opc/whereiskelley}"
BACKUP_ROOT="${WHEREISKELLEY_BACKUP_DIR:-/home/opc/whereiskelley-backups}"
BRANCH="${WHEREISKELLEY_DEPLOY_BRANCH:-main}"
SERVICE="${WHEREISKELLEY_SERVICE:-whereiskelley}"

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "Git repository not found: $APP_DIR" >&2
  exit 1
fi

if pgrep -f "$APP_DIR/scripts/guide_discover_wine_lists.py" >/dev/null 2>&1; then
  echo "Collection is running. Wait for it to finish before deploying." >&2
  exit 1
fi

shop_collection_running=0
if pgrep -f "$APP_DIR/scripts/wine_shop_collect.py" >/dev/null 2>&1; then
  shop_collection_running=1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$BACKUP_ROOT/$timestamp"
mkdir -p "$backup_dir"

cd "$APP_DIR"

sudo systemctl stop "$SERVICE"
service_stopped=1
restart_on_exit() {
  if [[ "${service_stopped:-0}" == "1" ]]; then
    sudo systemctl restart "$SERVICE" || true
  fi
}
trap restart_on_exit EXIT

if [[ -f .env.local ]]; then
  cp -p .env.local "$backup_dir/.env.local"
fi
if [[ -f db/starwine.sqlite ]]; then
  mkdir -p "$backup_dir/db"
  cp -p db/starwine.sqlite "$backup_dir/db/starwine.sqlite"
fi
if [[ "$shop_collection_running" == "0" && -f db/wine_shops.sqlite ]]; then
  mkdir -p "$backup_dir/db"
  cp -p db/wine_shops.sqlite "$backup_dir/db/wine_shops.sqlite"
elif [[ "$shop_collection_running" == "1" ]]; then
  echo "Wine-shop collection is running; leaving its ignored SQLite files in place."
fi
if [[ -d public/data ]]; then
  tar -czf "$backup_dir/public-data.tar.gz" public/data
fi

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [[ -f "$backup_dir/.env.local" ]]; then
  cp -p "$backup_dir/.env.local" .env.local
fi
if [[ -f "$backup_dir/db/starwine.sqlite" ]]; then
  mkdir -p db
  cp -p "$backup_dir/db/starwine.sqlite" db/starwine.sqlite
fi
if [[ -f "$backup_dir/db/wine_shops.sqlite" ]]; then
  mkdir -p db
  cp -p "$backup_dir/db/wine_shops.sqlite" db/wine_shops.sqlite
fi
if [[ -f "$backup_dir/public-data.tar.gz" ]]; then
  tar -xzf "$backup_dir/public-data.tar.gz" -C "$APP_DIR"
fi

sudo chown -R opc:opc "$APP_DIR"
sudo systemctl restart "$SERVICE"
service_stopped=0
trap - EXIT

sleep 2
curl -fsS http://127.0.0.1:4317/api/health >/dev/null

echo "Deployed $(git rev-parse --short HEAD)"
echo "Runtime backup: $backup_dir"
