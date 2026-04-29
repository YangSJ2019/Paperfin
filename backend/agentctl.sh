#!/usr/bin/env bash
# Paperfin LaunchAgent control script — manages both backend and frontend.
#
# Usage:
#   ./agentctl.sh start [backend|frontend|all]
#   ./agentctl.sh stop [backend|frontend|all]
#   ./agentctl.sh restart [backend|frontend|all]
#   ./agentctl.sh status [backend|frontend|all]
#   ./agentctl.sh logs <backend|frontend>
#   ./agentctl.sh kick <backend|frontend>
#
# Omitting the service name defaults to 'all'.

set -euo pipefail

DOMAIN="gui/$(id -u)"
BACKEND_LABEL="ai.paperfin.backend"
FRONTEND_LABEL="ai.paperfin.frontend"
BACKEND_LOG_DIR="$(cd "$(dirname "$0")" && pwd)/data/logs"
FRONTEND_LOG_DIR="$(cd "$(dirname "$0")/../frontend" && pwd)/logs"

# ---------- helpers --------------------------------------------------------

plist_for() {
  case "$1" in
    backend)  echo "$HOME/Library/LaunchAgents/${BACKEND_LABEL}.plist" ;;
    frontend) echo "$HOME/Library/LaunchAgents/${FRONTEND_LABEL}.plist" ;;
    *) echo "unknown service: $1" >&2; return 1 ;;
  esac
}

label_for() {
  case "$1" in
    backend)  echo "$BACKEND_LABEL" ;;
    frontend) echo "$FRONTEND_LABEL" ;;
    *) echo "unknown service: $1" >&2; return 1 ;;
  esac
}

pid_of() {
  launchctl print "${DOMAIN}/$(label_for "$1")" 2>/dev/null \
    | awk -F' = ' '/^\tpid/ {print $2; exit}'
}

is_loaded() {
  launchctl print "${DOMAIN}/$(label_for "$1")" &>/dev/null
}

do_start() {
  local svc="$1"
  if is_loaded "$svc"; then
    echo "[$svc] already loaded"
  else
    launchctl bootstrap "$DOMAIN" "$(plist_for "$svc")"
    echo "[$svc] loaded — will start on every login"
  fi
}

do_stop() {
  local svc="$1"
  if launchctl bootout "${DOMAIN}/$(label_for "$svc")" 2>/dev/null; then
    echo "[$svc] unloaded"
  else
    echo "[$svc] not loaded"
  fi
}

do_restart() {
  local svc="$1"
  launchctl bootout "${DOMAIN}/$(label_for "$svc")" 2>/dev/null || true
  sleep 1
  launchctl bootstrap "$DOMAIN" "$(plist_for "$svc")"
  echo "[$svc] reloaded"
}

do_status() {
  local svc="$1"
  if is_loaded "$svc"; then
    local pid
    pid=$(pid_of "$svc")
    if [[ -n "${pid:-}" ]]; then
      echo "[$svc] running — pid $pid"
    else
      echo "[$svc] loaded but not currently running (waiting to restart?)"
    fi
  else
    echo "[$svc] not loaded"
  fi
}

do_kick() {
  local svc="$1"
  local pid
  pid=$(pid_of "$svc")
  if [[ -n "${pid:-}" ]]; then
    kill "$pid" && echo "[$svc] sent SIGTERM to $pid — will auto-restart in ~10s"
  else
    echo "[$svc] not running"
  fi
}

do_logs() {
  local svc="$1"
  local dir
  case "$svc" in
    backend)  dir="$BACKEND_LOG_DIR" ;;
    frontend) dir="$FRONTEND_LOG_DIR" ;;
    *) echo "unknown service: $svc" >&2; exit 2 ;;
  esac
  tail -F "$dir/${svc}.err.log" "$dir/${svc}.out.log"
}

# ---------- dispatch -------------------------------------------------------

cmd="${1:-status}"
target="${2:-all}"

# Commands that require a single service (can't fan out).
case "$cmd" in
  logs|kick)
    if [[ "$target" == "all" ]]; then
      echo "$cmd requires a service: backend | frontend" >&2
      exit 2
    fi
    ;;
esac

case "$target" in
  all)      services=(backend frontend) ;;
  backend)  services=(backend) ;;
  frontend) services=(frontend) ;;
  *) echo "unknown service: $target (expected: backend | frontend | all)" >&2; exit 2 ;;
esac

case "$cmd" in
  start)   for s in "${services[@]}"; do do_start "$s"; done ;;
  stop)    for s in "${services[@]}"; do do_stop "$s"; done ;;
  restart) for s in "${services[@]}"; do do_restart "$s"; done ;;
  status)  for s in "${services[@]}"; do do_status "$s"; done ;;
  logs)    do_logs "$target" ;;
  kick)    do_kick "$target" ;;
  *)
    echo "usage: $0 {start|stop|restart|status} [backend|frontend|all]" >&2
    echo "       $0 {logs|kick} <backend|frontend>" >&2
    exit 2
    ;;
esac
