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

install_services() {
  echo "→ installing systemd services (auto-start on boot, auto-restart)"
  cat > /etc/systemd/system/pindrop.service <<EOF
[Unit]
Description=PinDrop Pro — Pinterest affiliate autopilot (24×7 scheduler)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$HERE
ExecStart=$HERE/.venv/bin/python -m bot run
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/pindrop-dashboard.service <<EOF
[Unit]
Description=PinDrop Pro — web dashboard (control panel + landing pages)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$HERE
ExecStart=$HERE/.venv/bin/python -m bot dashboard
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now pindrop.service
  systemctl enable --now pindrop-dashboard.service
  echo
  echo "✅ BOTH services live:"
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
