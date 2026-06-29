#!/data/data/com.termux/files/usr/bin/bash
# ════════════════════════════════════════════════════════════════════
#  XWALLET — Termux Launcher
#  Usage:
#    bash run_bot.sh          → start bot (prompts for .env if missing)
#    AUTO_LOGIN=true bash run_bot.sh  → skip all prompts, start immediately
#    bash run_bot.sh --setup  → interactive first-time setup wizard
# ════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

banner() {
  echo -e "${CYAN}${BOLD}"
  echo "  ╔═══════════════════════════════════╗"
  echo "  ║        ⚡  X W A L L E T         ║"
  echo "  ║   Multi-Coin Discord Wallet Bot   ║"
  echo "  ╚═══════════════════════════════════╝"
  echo -e "${RESET}"
}

log()  { echo -e "${GREEN}  ✅  $1${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠️   $1${RESET}"; }
err()  { echo -e "${RED}  ❌  $1${RESET}"; }
info() { echo -e "${CYAN}  ℹ️   $1${RESET}"; }

# ── Auto-login setting ────────────────────────────────────────────────────────
# Set AUTO_LOGIN=true in your shell or in .env to skip all prompts.
load_env() {
  if [ -f .env ]; then
    set -a; source .env; set +a
  fi
}
load_env

# AUTO_LOGIN can be set in shell environment OR inside .env
AUTO_LOGIN="${AUTO_LOGIN:-false}"

# ── Setup wizard ──────────────────────────────────────────────────────────────
setup_wizard() {
  echo -e "${BOLD}  🛠️  First-Time Setup Wizard${RESET}"
  echo ""
  if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example — fill in your values below."
  fi

  read -rp "  Discord Bot Token     : " _tok
  read -rp "  Owner Discord User ID : " _oid
  read -rp "  Bot Command Prefix [$] : " _pfx
  _pfx="${_pfx:-$}"

  sed -i "s|^DISCORD_TOKEN=.*|DISCORD_TOKEN=${_tok}|" .env
  sed -i "s|^OWNER_ID=.*|OWNER_ID=${_oid}|" .env
  sed -i "s|^BOT_PREFIX=.*|BOT_PREFIX=${_pfx}|" .env

  echo ""
  read -rp "  Enable Auto-Login? (skip this prompt next time) [y/N]: " _al
  if [[ "$_al" =~ ^[Yy]$ ]]; then
    if grep -q "^AUTO_LOGIN=" .env; then
      sed -i "s|^AUTO_LOGIN=.*|AUTO_LOGIN=true|" .env
    else
      echo "AUTO_LOGIN=true" >> .env
    fi
    log "Auto-Login ENABLED — next run will start immediately."
  fi

  echo ""
  log "Setup complete!  Run  bash run_bot.sh  to start."
  exit 0
}

# ── Handle --setup flag ───────────────────────────────────────────────────────
if [[ "$1" == "--setup" ]]; then
  banner
  setup_wizard
fi

# ── Dependency check ──────────────────────────────────────────────────────────
check_deps() {
  if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install with: pkg install python"
    exit 1
  fi
  if ! python3 -c "import discord" &>/dev/null 2>&1; then
    warn "discord.py not installed. Installing now…"
    pip install -r requirements.txt --quiet
  fi
}

# ── .env guard ────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  banner
  err ".env not found! Run:  bash run_bot.sh --setup"
  exit 1
fi

load_env  # reload after potential wizard changes
AUTO_LOGIN="${AUTO_LOGIN:-false}"

# ── Prompt (skipped if AUTO_LOGIN=true) ──────────────────────────────────────
banner
check_deps

if [[ "$AUTO_LOGIN" == "true" ]]; then
  info "Auto-Login is ON — starting immediately…"
  echo ""
else
  info "Auto-Login is OFF. Set AUTO_LOGIN=true in .env to skip this prompt."
  echo ""
  echo -e "  ${BOLD}Token configured:${RESET} ${DISCORD_TOKEN:0:12}…"
  echo -e "  ${BOLD}Owner ID        :${RESET} ${OWNER_ID}"
  echo ""
  read -rp "  Press ENTER to start, or Ctrl+C to cancel…" _dummy
  echo ""
fi

# ── Start ─────────────────────────────────────────────────────────────────────
log "Starting XWALLET Bot…"
echo ""

# Keep-alive loop: auto-restart on crash (up to 5 times, then wait 60s)
_crashes=0
while true; do
  python3 -m bot.main
  _exit=$?
  if [ $_exit -eq 0 ]; then
    info "Bot exited cleanly. Goodbye! 👋"
    break
  fi
  _crashes=$((_crashes + 1))
  warn "Bot crashed (exit $_exit). Restart #${_crashes}…"
  if [ $_crashes -ge 5 ]; then
    warn "5 crashes in a row — waiting 60s before retrying…"
    sleep 60
    _crashes=0
  else
    sleep 5
  fi
done
