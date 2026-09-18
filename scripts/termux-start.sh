#!/data/data/com.termux/files/usr/bin/bash
# Start the UAV web UI in Termux (Android).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "No .venv found. Run: make install"
  exit 1
fi

# Grant storage access once: termux-setup-storage
export UAV_WEB_HOST="${UAV_WEB_HOST:-0.0.0.0}"
export UAV_WEB_PORT="${UAV_WEB_PORT:-8765}"
export DOWNLOAD_DIR="${DOWNLOAD_DIR:-$HOME/storage/downloads}"

mkdir -p "$DOWNLOAD_DIR"
echo "Open http://127.0.0.1:${UAV_WEB_PORT}/ in your phone browser"
echo "Downloads -> $DOWNLOAD_DIR"
exec .venv/bin/python -m uav_downloader.web.server \
  --host "$UAV_WEB_HOST" \
  --port "$UAV_WEB_PORT"
