#!/bin/bash
# scripts/install_services.sh
# Installs VI Portfolio as systemd services (Linux / Jetson):
#   vi-portfolio-api        FastAPI backend on :8000
#   vi-portfolio-ui         Vite frontend on :5173
#   vi-portfolio-dime-sync  Dime Gmail import, run daily by vi-portfolio-dime-sync.timer
#   vi-portfolio-prices     store daily prices, run hourly by vi-portfolio-prices.timer
#   vi-portfolio-fundamentals  store statements + profiles, run weekly by vi-portfolio-fundamentals.timer
#
# usage: bash scripts/install_services.sh [--sync-time HH:MM] [--uninstall]
#   --sync-time  daily sync time in the system timezone (default 09:00)
# Re-run it after `git pull` or to change the sync time; it restarts the services.
set -euo pipefail

SYNC_TIME="09:00"
UNINSTALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --sync-time) SYNC_TIME="${2:-}"; shift $(( $# > 1 ? 2 : 1 )) ;;
        --uninstall) UNINSTALL=1; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

UNITS="vi-portfolio-api.service vi-portfolio-ui.service vi-portfolio-dime-sync.service vi-portfolio-dime-sync.timer vi-portfolio-prices.service vi-portfolio-prices.timer vi-portfolio-fundamentals.service vi-portfolio-fundamentals.timer"
STARTED="vi-portfolio-api.service vi-portfolio-ui.service vi-portfolio-dime-sync.timer vi-portfolio-prices.timer vi-portfolio-fundamentals.timer"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"

if [ "$UNINSTALL" = 1 ]; then
    for u in $STARTED; do sudo systemctl disable --now "$u" 2>/dev/null || true; done
    for u in $UNITS; do sudo rm -f "$UNIT_DIR/$u"; done
    sudo systemctl daemon-reload
    echo "Removed VI Portfolio services."
    exit 0
fi

if [ "$EUID" -eq 0 ]; then
    echo "Run this as your normal user (it calls sudo itself), so the services run as you."
    exit 1
fi

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_USER="$(id -un)"
PYTHON="$APP_DIR/.venv/bin/python"
NPX="$(command -v npx || true)"

# --- preflight -----------------------------------------------------------------
[[ "$APP_DIR" =~ [[:space:]%] ]] && { echo "The project path must not contain spaces or '%': $APP_DIR"; exit 1; }
[ -x "$PYTHON" ] || { echo "Missing $PYTHON. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
[ -n "$NPX" ] || { echo "npx not found in PATH. Install Node.js 20+ first."; exit 1; }
NODE="$(dirname "$NPX")/node"
"$NODE" -e 'process.exit(+process.versions.node.split(".")[0] >= 20 ? 0 : 1)' \
    || { echo "Node.js 20+ is required by Vite (found $("$NODE" --version 2>/dev/null || echo none))."; exit 1; }
[ -d "$APP_DIR/frontend/node_modules" ] || { echo "Missing frontend/node_modules. Run: cd frontend && npm install"; exit 1; }
[[ "$SYNC_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || { echo "--sync-time must be HH:MM (00:00-23:59)"; exit 1; }
for f in .env secrets/gmail_credentials.json secrets/gmail_token.json; do
    [ -f "$APP_DIR/$f" ] || echo "Warning: $f not found; the daily Dime sync will fail until it is copied here."
done
# the Gmail token is refreshed and rewritten on almost every sync
if [ -f "$APP_DIR/secrets/gmail_token.json" ] && [ ! -w "$APP_DIR/secrets/gmail_token.json" ]; then
    echo "secrets/gmail_token.json is not writable by $RUN_USER. Fix: sudo chown -R $RUN_USER $APP_DIR/secrets"
    exit 1
fi

# systemd starts with a minimal PATH; include node's directory (e.g. nvm installs)
SERVICE_PATH="$(dirname "$NPX"):/usr/local/bin:/usr/bin:/bin"
COMMON="User=$RUN_USER
Environment=PATH=$SERVICE_PATH
Environment=PYTHONUNBUFFERED=1"

write_unit() {  # name, content
    echo "$2" | sudo tee "$UNIT_DIR/$1" > /dev/null
    echo "  wrote $UNIT_DIR/$1"
}

echo "Installing for user '$RUN_USER' from $APP_DIR"

write_unit vi-portfolio-api.service "[Unit]
Description=VI Portfolio API (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
$COMMON
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON api/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target"

# --strictPort: if 5173 is taken, fail and retry instead of silently moving to 5174
write_unit vi-portfolio-ui.service "[Unit]
Description=VI Portfolio UI (Vite)
After=vi-portfolio-api.service

[Service]
$COMMON
WorkingDirectory=$APP_DIR/frontend
ExecStart=$NPX vite --host --strictPort
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target"

# time-sync: a sync caught up right after boot needs a correct clock for TLS/OAuth
write_unit vi-portfolio-dime-sync.service "[Unit]
Description=VI Portfolio: import new Dime PDFs from Gmail
After=network-online.target time-sync.target
Wants=network-online.target time-sync.target

[Service]
Type=oneshot
$COMMON
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON app/cli.py dime-sync"

write_unit vi-portfolio-dime-sync.timer "[Unit]
Description=Daily Dime import for VI Portfolio

[Timer]
OnCalendar=*-*-* $SYNC_TIME:00
Persistent=true

[Install]
WantedBy=timers.target"

write_unit vi-portfolio-prices.service "[Unit]
Description=VI Portfolio: store daily prices from Yahoo Finance
After=network-online.target time-sync.target
Wants=network-online.target time-sync.target

[Service]
Type=oneshot
$COMMON
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON app/cli.py prices-refresh"

write_unit vi-portfolio-prices.timer "[Unit]
Description=Hourly price refresh for VI Portfolio

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target"

write_unit vi-portfolio-fundamentals.service "[Unit]
Description=VI Portfolio: store financial statements and profiles from Yahoo Finance
After=network-online.target time-sync.target
Wants=network-online.target time-sync.target

[Service]
Type=oneshot
$COMMON
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON app/cli.py fundamentals-refresh"

# weekly: statements only change quarterly; Sunday morning avoids both markets' sessions
write_unit vi-portfolio-fundamentals.timer "[Unit]
Description=Weekly fundamentals refresh for VI Portfolio

[Timer]
OnCalendar=Sun *-*-* 06:30:00
Persistent=true

[Install]
WantedBy=timers.target"

sudo systemctl daemon-reload
sudo systemctl enable $STARTED
sudo systemctl restart $STARTED   # pick up changed units / code on re-install
sudo systemctl start --no-block vi-portfolio-prices.service   # backfill now instead of at the next hour
sudo systemctl start --no-block vi-portfolio-fundamentals.service

sleep 5
for u in vi-portfolio-api.service vi-portfolio-ui.service; do
    systemctl is-active --quiet "$u" || { echo "$u failed to start. See: journalctl -u $u -n 50"; exit 1; }
done

if systemctl is-enabled --quiet vi-portfolio.service 2>/dev/null; then
    echo "Note: the old Streamlit service (vi-portfolio.service) is still enabled."
    echo "      Disable it with: sudo systemctl disable --now vi-portfolio.service"
fi

echo
echo "Done. Don't also run run_local.sh: it needs the same ports (8000, 5173)."
echo "Useful commands:"
echo "  systemctl status vi-portfolio-api vi-portfolio-ui"
echo "  systemctl list-timers vi-portfolio-dime-sync.timer     # next sync time"
echo "  sudo systemctl start vi-portfolio-dime-sync            # sync now"
echo "  journalctl -u vi-portfolio-dime-sync -n 100            # last sync result"
echo "  journalctl -u vi-portfolio-prices -n 50                # last price refresh"
echo "  journalctl -u vi-portfolio-fundamentals -n 50          # last fundamentals refresh"
