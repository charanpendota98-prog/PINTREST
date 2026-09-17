#!/usr/bin/env bash
# 🛰 PinDrop Pro 24×7 guardian — installs deps, auto-restarts on crash.
# Usage:  nohup ./run.sh > pindrop.log 2>&1 &
cd "$(dirname "$0")" || exit 1

if [ ! -d .venv ]; then
  echo "→ creating venv…"
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet -r requirements.txt imageio-ffmpeg

while true; do
  .venv/bin/python -m bot run
  echo "⚠ bot exited ($(date)) — restarting in 10s…"
  sleep 10
done
