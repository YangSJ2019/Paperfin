#!/usr/bin/env bash
# Install macOS LaunchAgents for Paperfin so backend + frontend start at login
# and restart on crash. Optional — you can also just run `./agentctl.sh start`
# manually.
#
# What it does:
#   1. Reads launchd/ai.paperfin.*.plist.template from this repo
#   2. Substitutes __PROJECT_ROOT__ with the absolute path to your checkout
#   3. Substitutes __NODE_BIN__ / __NODE_DIR__ with the Node binary it resolves
#      via `which node` (nvm / volta / brew-installed node all work)
#   4. Writes the rendered plists to ~/Library/LaunchAgents/
#   5. Lints them with `plutil` and loads them with `launchctl bootstrap`
#
# Uninstall:
#   cd backend && ./agentctl.sh stop all
#   rm ~/Library/LaunchAgents/ai.paperfin.*.plist

set -euo pipefail

# Repo root (one level up from this script)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"

# --- Sanity checks ---------------------------------------------------------

if [[ ! -d "$REPO_ROOT/backend/.venv" ]]; then
  cat >&2 <<EOF
error: backend/.venv not found at $REPO_ROOT/backend/.venv
       Run these first from the repo root:
           cd backend
           python3.12 -m venv .venv
           .venv/bin/pip install -e .
EOF
  exit 1
fi

if [[ ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
  cat >&2 <<EOF
error: frontend/node_modules not found.
       Run these first:
           cd frontend && npm install
EOF
  exit 1
fi

NODE_BIN="$(command -v node || true)"
if [[ -z "$NODE_BIN" ]]; then
  echo "error: 'node' not on PATH. Install Node 18+ (nvm / volta / brew)." >&2
  exit 1
fi
NODE_DIR="$(dirname "$NODE_BIN")"

mkdir -p "$LAUNCHD_DIR"

# --- Render templates ------------------------------------------------------

render() {
  local template="$1" target="$2"
  sed \
    -e "s|__PROJECT_ROOT__|${REPO_ROOT}|g" \
    -e "s|__NODE_BIN__|${NODE_BIN}|g" \
    -e "s|__NODE_DIR__|${NODE_DIR}|g" \
    "$template" > "$target"
  plutil -lint "$target" >/dev/null
  echo "  rendered $target"
}

echo "Installing LaunchAgents into $LAUNCHD_DIR"
render "$REPO_ROOT/launchd/ai.paperfin.backend.plist.template" \
       "$LAUNCHD_DIR/ai.paperfin.backend.plist"
render "$REPO_ROOT/launchd/ai.paperfin.frontend.plist.template" \
       "$LAUNCHD_DIR/ai.paperfin.frontend.plist"

# --- Load ------------------------------------------------------------------

DOMAIN="gui/$(id -u)"

for label in ai.paperfin.backend ai.paperfin.frontend; do
  # Unload if already loaded so we pick up the new rendering
  if launchctl print "${DOMAIN}/${label}" &>/dev/null; then
    launchctl bootout "${DOMAIN}/${label}" 2>/dev/null || true
    sleep 0.3
  fi
  launchctl bootstrap "$DOMAIN" "$LAUNCHD_DIR/${label}.plist"
  echo "  loaded $label"
done

echo
echo "Done. Check status with:"
echo "    cd $REPO_ROOT/backend && ./agentctl.sh status"
echo
echo "Backend: http://localhost:8000/health"
echo "Frontend: http://localhost:5173"
