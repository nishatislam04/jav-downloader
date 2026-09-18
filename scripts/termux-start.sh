#!/data/data/com.termux/files/usr/bin/bash
# Start the web UI in Termux — same as: make web
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "No .venv found. Run: make install"
  exit 1
fi

# Grant storage access once: termux-setup-storage
exec make web
