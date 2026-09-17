#!/usr/bin/env bash
# 🚀 One-command VPS deploy — installs everything + systemd 24×7 service.
# Usage on your VPS/PC (Ubuntu/Debian):  sudo ./deploy.sh
set -e
cd "$(dirname "$0")"

echo "→ venv + deps"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt imageio-ffmpeg

if [ "$(id -u)" = "0" ] && [ -d /etc/systemd/system ]; then
  echo "→ installing systemd service (auto-start on boot, auto-restart on crash)"
  cat > /etc/systemd/system/pindrop.service <<EOF
[Unit]
Description=PinDrop Pro Pinterest Affiliate Autopilot
After=network.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python -m bot run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now pindrop.service
  echo "✅ Service running:  systemctl status pindrop   |  logs: journalctl -fu pindrop"
else
  echo "→ (not root or no systemd) using run.sh guardian instead"
  nohup ./run.sh > pindrop.log 2>&1 &
  echo "✅ Guardian started (pindrop.log)"
fi
echo
echo "🎉 FULLY SET. Dashboard: python -m bot dashboard  (port 5000)"
