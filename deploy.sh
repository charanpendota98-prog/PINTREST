#!/usr/bin/env bash
# 🚀 One-command VPS deploy — installs everything + runs BOTH services 24×7:
#    1) pindrop           → the posting autopilot (python -m bot run)
#    2) pindrop-dashboard → the web control panel (python -m bot dashboard)
# Both auto-start on boot and auto-restart on any crash.
# Usage on your VPS (Ubuntu/Debian):   sudo ./deploy.sh
set -e
cd "$(dirname "$0")"
HERE="$(pwd)"

echo "→ venv + dependencies"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt imageio-ffmpeg

echo "→ sanity checks"
.venv/bin/python -m bot doctor || true

# Oracle Always-Free instances are RECLAIMED when they look idle for 7 days
# (CPU 95th percentile < 10%). `sudo ./deploy.sh --keepalive` installs a third
# service that keeps the box measurably busy. Not needed on a PAYG account.
KEEPALIVE=""
for a in "$@"; do
  [ "$a" = "--keepalive" ] && KEEPALIVE="1"
done

install_services() {
  echo "→ installing systemd services (auto-start on boot, auto-restart)"
  # Never run the bot as root: use the human who called sudo (fallback: root).
  RUN_USER="${SUDO_USER:-root}"
  if [ "$RUN_USER" != "root" ] && id "$RUN_USER" >/dev/null 2>&1; then
    RUN_GROUP="$(id -gn "$RUN_USER")"
  else
    RUN_USER="root"; RUN_GROUP="root"
  fi
  mkdir -p data logs
  chown -R "$RUN_USER:$RUN_GROUP" data logs 2>/dev/null || true
  cat > /etc/systemd/system/pindrop.service <<EOF
[Unit]
Description=PinDrop Pro — Pinterest affiliate autopilot (24×7 scheduler)
StartLimitIntervalSec=300
StartLimitBurst=10
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$HERE
ExecStart=$HERE/.venv/bin/python -m bot run
Restart=on-failure
RestartSec=15
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/pindrop-dashboard.service <<EOF
[Unit]
Description=PinDrop Pro — web dashboard (control panel + landing pages)
StartLimitIntervalSec=300
StartLimitBurst=10
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$HERE
ExecStart=$HERE/.venv/bin/python -m bot dashboard
Restart=on-failure
RestartSec=15
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  if [ -n "$KEEPALIVE" ]; then
    cat > /etc/systemd/system/pindrop-keepalive.service <<EOF
[Unit]
Description=PinDrop Pro — Oracle idle-reclaim guard (CPU duty cycle)
After=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$HERE
ExecStart=$HERE/.venv/bin/python -m bot keepalive
Restart=always
RestartSec=20
Nice=10
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  fi

  systemctl daemon-reload
  systemctl enable --now pindrop.service
  systemctl enable --now pindrop-dashboard.service
  if [ -n "$KEEPALIVE" ]; then
    systemctl enable --now pindrop-keepalive.service
    echo "🛡 idle-guard ON (pindrop-keepalive) — Oracle reclaim rule padadu"
  fi
  echo
  echo "✅ BOTH services live (running as user: $RUN_USER):"
  echo "   systemctl status pindrop             # scheduler"
  echo "   systemctl status pindrop-dashboard   # dashboard"
  echo "   journalctl -fu pindrop               # live logs (posting)"
  echo "   journalctl -fu pindrop-dashboard     # live logs (dashboard)"
}

start_guardians() {
  echo "→ no systemd/root — starting guardian processes instead"
  mkdir -p logs
  nohup ./run.sh > logs/guardian.log 2>&1 &
  echo "✅ guardians started (logs/guardian.log) — dashboard + scheduler"
}

if [ "$(id -u)" = "0" ] && [ -d /etc/systemd/system ] && command -v systemctl >/dev/null; then
  install_services
else
  start_guardians
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "🎉 FULLY SET"
echo "   Dashboard : http://${IP:-localhost}:5000"
echo "   Landing   : http://${IP:-localhost}:5000/go/1   (bridge link per product)"
echo "   Deals list: http://${IP:-localhost}:5000/deals/today"
echo
echo "   Next: python -m bot simulate    → must print 🏆 SIMULATION PASSED"
echo "   Then: python -m bot how         → what the machine does, every day"
echo
echo "🔐 Panel login (admin area is password-locked; /go/… pages stay public):"
echo "   .venv/bin/python -m bot dashboard-pass"
echo "   → prints URL + password (auto-created on first run)"
echo
echo "🚦 Anything missing? one command says it all:"
echo "   .venv/bin/python -m bot deploy-check"
