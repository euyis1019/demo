#!/usr/bin/env bash
# Stop HBM Demo background processes (Runner / Flask / Vite).
# Safe to run repeatedly — PLAN2 F6-2.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=demo_ports.sh
source "$SCRIPT_DIR/demo_ports.sh"
RUN_DIR="$SCRIPT_DIR/../.run"
PID_FILE="$RUN_DIR/demo.pids"

kill_pid() {
  local pid="$1"
  [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]] && return 0
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.2
  done
  kill -9 "$pid" 2>/dev/null || true
}

if [[ -f "$PID_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$PID_FILE"
  kill_pid "${RUNNER_PID:-}"
  kill_pid "${FLASK_PID:-}"
  kill_pid "${VITE_PID:-}"
  if [[ -n "${FLASK_PORT:-}" ]]; then
    pkill -f "flask run --host 127.0.0.1 --port ${FLASK_PORT}" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

# Fallback: pattern cleanup (handles orphaned demo processes only).
pkill -f "agent_world.hbm_demo.run_hbm.*hbm_memory_war" 2>/dev/null || true
for port in $(seq "$HBM_DEMO_FLASK_PORT_DEFAULT" "$HBM_DEMO_FLASK_PORT_MAX"); do
  pkill -f "flask run --host 127.0.0.1 --port ${port}" 2>/dev/null || true
done
pkill -f "vite --host 127.0.0.1" 2>/dev/null || true

exit 0
