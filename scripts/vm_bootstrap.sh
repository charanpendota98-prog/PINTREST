#!/usr/bin/env bash
# 🚀 PinDrop / Gharvanaa — one-command setup for a FRESH cloud VM
#    (tested target: Oracle Cloud "Always Free" ARM Ampere or AMD micro,
#     Ubuntu 22.04/24.04 LTS; also works on Debian, Oracle Linux, Fedora)
#
# What it does, in order:
#   1. installs system packages: git, python3-venv, ffmpeg, curl
#   2. creates the virtualenv + installs requirements
#   3. prepares data/ + logs/ and copies .env.example → .env (chmod 600)
#   4. tells you EXACTLY what to paste into .env (nothing is invented)
#   5. with root: installs BOTH systemd services (24×7, auto-restart on boot)
#      without root: starts ./run.sh (guardian processes)
#
# Usage:
#   git clone <repo> pintrest && cd pintrest
#   bash scripts/vm_bootstrap.sh
#
# Safe to re-run: every step checks before it acts.
set -euo pipefail
cd "$(dirname "$0")/.."
HERE="$(pwd)"
SKIP_START=""
[ "${1:-}" = "--no-start" ] && SKIP_START="1"

say()  { printf '\n\033[1;36m→ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✅ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠️  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m❌ %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. sanity
# must actually be the repo (running this file from /tmp used to create /.venv)
if [ ! -f requirements.txt ] || [ ! -d bot ]; then
  die "Idi repo root kaadu (${HERE}). 'cd' chesi repo folder nunchi run cheyyandi:  bash scripts/vm_bootstrap.sh"
fi
say "Machine: $(uname -m) · $( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || echo 'unknown OS')"
TOTAL_MB="$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo 0)"
if [ "${TOTAL_MB:-0}" -gt 0 ] && [ "$TOTAL_MB" -lt 900 ]; then
  warn "RAM ${TOTAL_MB}MB (E2.1.Micro class) — swap ＋ settings tho pani chestundi."
  warn "Better: Oracle A1.Flex (Ampere) 2 OCPU/12GB — Always Free, reels 10× fast."
  warn "Idle-reclaim guard kuda pettandi: sudo ./deploy.sh --keepalive"
fi

# ------------------------------------------------------ 0b. swap (low RAM)
# Oracle's free micro shape has 1 GB RAM. Rendering a 720×1280 reel (PIL +
# ffmpeg) can spike past that, and the kernel OOM-killer would kill the
# scheduler mid-post. A swap file makes the small box boring but reliable.
setup_swap() {
  local total_mb="$1"
  if [ "${total_mb:-0}" -ge 3500 ]; then return 0; fi
  if swapon --show 2>/dev/null | grep -q .; then ok "swap already active"; return 0; fi
  say "RAM ${total_mb}MB → 2 GB swap file create chestunnanu (reels safe)"
  if ! $SUDO fallocate -l 2G /swapfile 2>/dev/null; then
    $SUDO dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none || {
      warn "swap file create fail — memory low ga undi, reels slow avvachu"; return 0; }
  fi
  $SUDO chmod 600 /swapfile
  $SUDO mkswap /swapfile >/dev/null
  $SUDO swapon /swapfile || { warn "swapon fail — continue"; return 0; }
  grep -q '^/swapfile' /etc/fstab || \
    echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
  echo 'vm.swappiness=20' | $SUDO tee /etc/sysctl.d/99-pindrop-swap.conf >/dev/null || true
  $SUDO sysctl -q vm.swappiness=20 2>/dev/null || true
  ok "swap ready: $(free -m 2>/dev/null | awk '/Swap:/{print $2" MB"}')"
}
if [ "${TOTAL_MB:-0}" -gt 0 ]; then setup_swap "$TOTAL_MB"; fi

# ------------------------------------------------------- 1. system packages
SUDO=""
if [ "$(id -u)" != "0" ]; then command -v sudo >/dev/null && SUDO="sudo"; fi
# Package install is BEST-EFFORT on purpose: a sandbox/offline box must never
# abort the whole setup because apt could not reach a mirror. pip wheels cover
# most of it (imageio-ffmpeg bundles its own binary on x86_64), so we install
# what we can, then VERIFY at the end and say exactly what is missing.
install_pkgs() {
  if command -v apt-get >/dev/null; then
    $SUDO apt-get update -y -qq || warn "apt update fail (offline mirror?) — continue"
    $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      python3 python3-venv python3-pip git curl ca-certificates \
      || warn "apt packages partial — continue"
    $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg \
      || warn "ffmpeg install fail — bundled ffmpeg try chestam"
  elif command -v dnf >/dev/null; then
    $SUDO dnf install -y -q python3 python3-pip git curl || true
    $SUDO dnf install -y -q ffmpeg || warn "ffmpeg install fail — bundled try"
  elif command -v yum >/dev/null; then
    $SUDO yum install -y -q python3 python3-pip git curl || true
    $SUDO yum install -y -q ffmpeg || warn "ffmpeg install fail — bundled try"
  else
    warn "Teliyani package manager — git/python3/ffmpeg ni nuvve install cheyyandi."
  fi
}
say "Step 1/5 — system packages (git, python3-venv, ffmpeg)"
if command -v python3 >/dev/null && command -v git >/dev/null; then
  ok "already installed: $(python3 -V)$(command -v ffmpeg >/dev/null && echo " + $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)" || echo " (ffmpeg ledu — bundled try chestam)")"
else
  install_pkgs
  command -v python3 >/dev/null || die "python3 install avvaledu — 'sudo apt install python3 python3-venv' chesi malli run cheyyandi"
  ok "packages ready"
fi

# ------------------------------------------------------------- 2. venv + pip
say "Step 2/5 — virtualenv + requirements (2-4 min, okasari)"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt
ok "python packages installed"
if ./.venv/bin/python -c "from bot.video_maker import ffmpeg_exe; print('   🎬 ffmpeg:', ffmpeg_exe())" 2>/dev/null; then
  :
else
  warn "ffmpeg ledu (reels render avvavu, pins + links pani chestayi)."
  warn "Fix: sudo apt install ffmpeg   (tarvata: ./run.sh stop && ./run.sh)"
fi

# --------------------------------------------------------------- 3. folders
say "Step 3/5 — data/ + logs/"
mkdir -p data/media logs
[ -f data/dashboard_password.txt ] || \
  printf 'ChangeMe-%s' "$(date +%s | tail -c 7)" > data/dashboard_password.txt
chmod 600 data/dashboard_password.txt
ok "data/ logs/ ready (panel password: data/dashboard_password.txt)"

# ------------------------------------------------------------------ 4. .env
say "Step 4/5 — secrets file"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  warn ".env kotha ga create chesanu — EEVEEVI paste cheyyandi:"
  cat <<'KEYS'

  ┌─ .env (nano .env) ────────────────────────────────────────────────┐
  │ MEESHO_TEMPLATE_LINK=…   (Meesho → Share → copy; 2-4 links, comma) │
  │ AMAZON_TAG=mama086-21                                              │
  │ EARNKARO_API_TOKEN=…     (optional, direct commission)             │
  │ PINTEREST_ACCESS_TOKEN=… (python -m bot auth tarvata)              │
  │ INSTAGRAM_ACCESS_TOKEN=… / IG_USER_ID=…                            │
  │ FACEBOOK_ACCESS_TOKEN=…  / FACEBOOK_PAGE_ID=…                      │
  │ TELEGRAM_TOKEN=…         / TELEGRAM_CHAT_ID=…                      │
  │ TELEGRAM_DEALS_CHANNEL=@yourchannel                                │
  └────────────────────────────────────────────────────────────────────┘

KEYS
else
  chmod 600 .env
  KEYS_SET="$(grep -cE '^(TELEGRAM_TOKEN|AMAZON_TAG|MEESHO_TEMPLATE_LINK)=.+' .env || true)"
  ok ".env already undi (${KEYS_SET} important key(s) set)"
fi

# ------------------------------------------------------------- 5. run 24×7
say "Step 5/5 — 24×7 ga start cheyyadam"
if [ -n "$SKIP_START" ]; then
  warn "--no-start: services start cheyyaledu (setup matrame)"
elif [ "$(id -u)" = "0" ] && command -v systemctl >/dev/null; then
  ./deploy.sh
elif command -v systemctl >/dev/null && [ -n "$SUDO" ]; then
  $SUDO ./deploy.sh
else
  nohup ./run.sh > logs/guardian.log 2>&1 &
  sleep 3
  ./run.sh status || true
fi

cat <<'DONE'

──────────────────────────────────────────────────────────────────────
✅ SETUP DONE. Next:

  1) Browser lo panel (SSH tunnel tho — port ni internet ki open cheyyaku):
       ssh -L 5000:127.0.0.1:5000 ubuntu@<vm-ip>
       → http://localhost:5000   (password: data/dashboard_password.txt)

  2) Phone nunchi Telegram control:
       Telegram lo nee bot ki /start → /status

  3) Status eppudaina:
       ./run.sh status          (guardian mode)
       sudo systemctl status pindrop pindrop-dashboard   (systemd mode)
       ./.venv/bin/python -m bot doctor

  4) Logs:
       tail -f logs/guardian.log   |   sudo journalctl -u pindrop -f

  5) 🛡 Oracle free-tier idle-guard (reclaim rule — CPU <10% for 7 days):
       sudo ./deploy.sh --keepalive     # 3rd systemd service, keeps box busy
     (Pay-As-You-Go account aithe idi avasaram ledu.)
──────────────────────────────────────────────────────────────────────
DONE
