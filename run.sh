#!/usr/bin/env bash
# 🛰 PinDrop Pro 24×7 guardian — runs BOTH services and restarts either one if
# it ever dies, while making sure there can never be TWO of them.
#
#   ./run.sh          start (idempotent: a second call refuses politely)
#   ./run.sh status   are the poster + panel alive?
#   ./run.sh stop     stop everything (guardians + children)
#
# Usage on a VPS:   nohup ./run.sh > logs/guardian.log 2>&1 &
# With root+systemd use `sudo ./deploy.sh` instead — it installs real services.
set -u
cd "$(dirname "$0")" || exit 1
mkdir -p logs
LOCK="logs/.guardian.pid"
PORT="5000"
PY=".venv/bin/python"

pid_alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

guardian_pid() {                       # prints the live guardian pid, if any
  [ -f "$LOCK" ] || return 1
  local p; p="$(cat "$LOCK" 2>/dev/null || true)"
  pid_alive "$p" || { rm -f "$LOCK"; return 1; }
  echo "$p"
}

systemd_active() {
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl is-active --quiet pindrop 2>/dev/null && return 0
  systemctl is-active --quiet pindrop-dashboard 2>/dev/null && return 0
  return 1
}

case "${1:-start}" in
  stop)
    if systemd_active; then
      echo "⚠️  systemd services are ACTIVE (pindrop / pindrop-dashboard)."
      echo "   This script must not kill them — use:"
      echo "     sudo systemctl stop pindrop pindrop-dashboard"
      exit 1
    fi
    G="$(guardian_pid || true)"
    echo "→ stopping guardians + children…"
    [ -n "${G:-}" ] && kill -TERM "$G" 2>/dev/null
    sleep 1
    # children: only OUR commands, never the caller's shell
    pkill -f "python -m bot run" 2>/dev/null || true
    pkill -f "python -m bot dashboard" 2>/dev/null || true
    [ -n "${G:-}" ] && kill -KILL "$G" 2>/dev/null
    rm -f "$LOCK"
    echo "✅ stopped (check: ss -ltn | grep :$PORT)"
    exit 0
    ;;
  status)
    G="$(guardian_pid || true)"
    if [ -n "${G:-}" ]; then echo "✅ guardian running (pid $G)"; else echo "❌ guardian not running"; fi
    if pgrep -f "python -m bot run" >/dev/null 2>&1; then echo "✅ poster (scheduler) alive"; else echo "❌ poster (scheduler) not running"; fi
    if curl -fsS -m 3 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
      echo "✅ panel answering on :$PORT"
      curl -fsS -m 3 "http://127.0.0.1:$PORT/healthz" 2>/dev/null; echo
    else
      echo "❌ panel not answering on :$PORT"
    fi
    exit 0
    ;;
esac

G="$(guardian_pid || true)"
if [ -n "${G:-}" ]; then
  echo "⏸  Guardian already running (pid $G) — nothing to start."
  echo "   status: ./run.sh status     stop: ./run.sh stop"
  exit 0
fi

if [ ! -d .venv ]; then
  echo "→ creating venv…"
  python3 -m venv .venv
fi
if ! "$PY" -c "import flask, PIL, requests, bs4, yaml" >/dev/null 2>&1; then
  echo "→ installing dependencies…"
  "$PY" -m pip install --quiet -r requirements.txt imageio-ffmpeg
fi

echo "$$" > "$LOCK"

DASH_PID=""
cleanup() {
  echo "→ guardian stopping…"
  [ -n "$DASH_PID" ] && kill -TERM "$DASH_PID" 2>/dev/null
  pkill -f "python -m bot run" 2>/dev/null || true
  pkill -f "python -m bot dashboard" 2>/dev/null || true
  rm -f "$LOCK"
  exit 0
}
trap cleanup INT TERM

# ── dashboard guardian ───────────────────────────────────────────────────
echo "→ dashboard guardian starting (logs/dashboard.log)"
(
  fail=0
  while true; do
    if curl -fsS -m 3 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
      echo "⚠ $PORT already answers /healthz — another panel is live; not starting a twin ($(date))" >> logs/dashboard.log
      sleep 30
      continue
    fi
    "$PY" -m bot dashboard >> logs/dashboard.log 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
      # clean exit usually means "another instance holds the lock" — back off
      echo "ℹ dashboard exited cleanly (duplicate guard) — sleeping 30s ($(date))" >> logs/dashboard.log
      fail=0; sleep 30
    else
      fail=$((fail + 1))
      if tail -n 5 logs/dashboard.log 2>/dev/null | grep -q "Address already in use"; then
        echo "❌ port $PORT is held by ANOTHER program (not our panel)." >> logs/dashboard.log
        echo "   Fix: change dashboard.port in config.yaml, or free the port ($(date))" >> logs/dashboard.log
        sleep 120
      else
        echo "⚠ dashboard crashed (rc=$rc, #$fail) — restarting in 10s ($(date))" >> logs/dashboard.log
        sleep 10
      fi
    fi
  done
) &
DASH_PID=$!

# ── scheduler guardian (plus a watchdog on the dashboard guardian) ───────
echo "→ scheduler guardian starting"
fail=0
while true; do
  "$PY" -m bot run
  rc=$?
  if [ "$rc" -eq 0 ]; then
    # our own duplicate guard said another autopilot owns the lock: do NOT
    # hammer the API, just wait — the twin will disappear or we take over.
    echo "ℹ scheduler exited cleanly (another autopilot holds the lock) — 30s ($(date))"
    sleep 30
  else
    fail=$((fail + 1))
    echo "⚠ scheduler crashed (rc=$rc, #$fail) — restarting in 10s ($(date))"
    sleep 10
  fi
  if ! pid_alive "$DASH_PID"; then
    echo "⚠ dashboard guardian died — restarting it"
    ( while true; do "$PY" -m bot dashboard >> logs/dashboard.log 2>&1; sleep 10; done ) &
    DASH_PID=$!
  fi
done
