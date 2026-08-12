#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${WHEREISKELLEY_APP_DIR:-/home/opc/whereiskelley}"

sudo install -m 0644 "$APP_DIR/deploy/whereiskelley-shop-inventory.service" /etc/systemd/system/whereiskelley-shop-inventory.service
sudo install -m 0644 "$APP_DIR/deploy/whereiskelley-shop-inventory.timer" /etc/systemd/system/whereiskelley-shop-inventory.timer
sudo systemctl daemon-reload
sudo systemctl enable --now whereiskelley-shop-inventory.timer
sudo systemctl list-timers whereiskelley-shop-inventory.timer --no-pager
