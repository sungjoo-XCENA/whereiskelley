#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${WHEREISKELLEY_APP_DIR:-/home/opc/whereiskelley}"

sudo install -m 0644 "$APP_DIR/deploy/whereiskelley-weekly.service" /etc/systemd/system/whereiskelley-weekly.service
sudo install -m 0644 "$APP_DIR/deploy/whereiskelley-weekly.timer" /etc/systemd/system/whereiskelley-weekly.timer
sudo systemctl daemon-reload
sudo systemctl enable --now whereiskelley-weekly.timer
sudo systemctl list-timers whereiskelley-weekly.timer --no-pager
