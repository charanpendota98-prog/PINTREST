#!/usr/bin/env bash
# 🛰 PinDrop Pro 24×7 guardian — runs BOTH the autopilot and the dashboard,
# restarting either one if it ever exits.
# Usage:  nohup ./run.sh > logs/guardian.log 2>&1 &
cd "$(dirname "$0")" || exit 1
mkdir -p logs

if [ ! -d .venv ]; then
  echo "→ creating venv…"
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet -r requirements.txt imageio-ffmpeg

echo "→ dashboard guardian starting (logs/dashboard.log)"
(
  while true; do
    .venv/bin/python -m bot dashboard >> logs/dashboard.log 2>&1
    echo "⚠ dashboard exited ($(date)) — restarting in 10s…" >> logs/dashboard.log
    sleep 10
  done
) &
DASH_PID=$!

cleanup() {
  echo "→ stopping (guardian)…"
  kill "$DASH_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "→ scheduler guardian starting"
while true; do
  .venv/bin/python -m bot run
  echo "⚠ scheduler exited ($(date)) — restarting in 10s…"
  sleep 10
done
