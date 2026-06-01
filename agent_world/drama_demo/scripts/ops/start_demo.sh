#!/usr/bin/env bash
# HBM Demo one-line launcher — PLAN2 F6-1 / Appendix C.
# Run from repository root:
#   ./agent_world/drama_demo/scripts/start_demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
WEB_DIR="$ROOT/agent_world/drama_demo/web"
DRAMA_DIR="$ROOT/agent_world/drama_demo"
RUN_DIR="$SCRIPT_DIR/../.run"
PID_FILE="$RUN_DIR/demo.pids"
STOP_SCRIPT="$SCRIPT_DIR/stop_demo.sh"
# shellcheck source=demo_ports.sh
source "$SCRIPT_DIR/demo_ports.sh"

VITE_PORT="${VITE_PORT:-$DRAMA_DEMO_VITE_PORT_DEFAULT}"

RUNNER_PID=""
FLASK_PID=""
FLASK_PORT=""

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" != *=* ]] && continue
    local key="${line%%=*}"
    local val="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    if [[ -z "${!key:-}" ]]; then
      export "$key=$val"
    fi
  done < "$file"
}

resolve_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  command -v python
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "错误: 未找到命令 '$1'。请先安装后再试。" >&2
    exit 1
  fi
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

pick_flask_port() {
  local port="${FLASK_RUN_PORT:-}"
  if [[ -n "$port" ]]; then
    if port_in_use "$port"; then
      echo "错误: FLASK_RUN_PORT=${port} 已被占用。" >&2
      exit 1
    fi
    echo "$port"
    return
  fi
  for ((port = DRAMA_DEMO_FLASK_PORT_DEFAULT; port <= DRAMA_DEMO_FLASK_PORT_MAX; port++)); do
    if ! port_in_use "$port"; then
      echo "$port"
      return
    fi
  done
  echo "错误: ${DRAMA_DEMO_FLASK_PORT_DEFAULT}-${DRAMA_DEMO_FLASK_PORT_MAX} 均无可用端口。" >&2
  exit 1
}

cleanup() {
  "$STOP_SCRIPT" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

cd "$ROOT"
mkdir -p "$RUN_DIR"

load_env_file "$DRAMA_DIR/.env"
load_env_file "$ROOT/agent_world/demo/.env"

require_cmd node
require_cmd npm

PYTHON="$(resolve_python)"
if ! "$PYTHON" -c "import agent_world" 2>/dev/null; then
  echo "错误: 无法 import agent_world。请在仓库根目录执行:" >&2
  echo "  pip install -e .   # 或 uv sync" >&2
  exit 1
fi

if [[ -z "${DMXAPI_KEY:-}" ]]; then
  echo "警告: 未设置 DMXAPI_KEY。Turn 1 的 LLM 打分与 NPC 响应可能失败。" >&2
  echo "  请 export DMXAPI_KEY=sk-... 或复制 .env.example 到 drama_demo/.env" >&2
fi

NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  echo "错误: 需要 Node.js 18+（当前 $(node -v)）。" >&2
  exit 1
fi

FLASK_PORT="$(pick_flask_port)"
# 大厅就绪探针：不带 sim_id（此刻还没选故事），用 /lobby/stories 判 Flask 是否起来。
HEALTH_URL="http://127.0.0.1:${FLASK_PORT}/api/drama/lobby/stories"

if port_in_use "$VITE_PORT"; then
  echo "错误: 端口 ${VITE_PORT} 已被占用（前端 dev server）。" >&2
  exit 1
fi

# E8 — repeatable start: clean stale processes first.
"$STOP_SCRIPT" >/dev/null 2>&1 || true

# 大厅模型：不预启动 Runner——玩家在前端「选择/新建故事」并激活后，由 WorldManager 按需为
# 该故事拉起对应 Runner（/api/drama/lobby/activate）。这里只起 Flask + 前端；故事世界的 Runner
# 生命周期完全交给大厅。注意：不导出 DRAMA_SIM_DIR，让 Flask 读路径跟随激活的故事（见 active_game）。
export FLASK_APP=agent_world.app:create_app
export FLASK_RUN_PORT="$FLASK_PORT"
export VITE_API_PROXY_TARGET="http://127.0.0.1:${FLASK_PORT}"
export VITE_PORT="$VITE_PORT"

  echo "正在启动 Flask（端口 ${FLASK_PORT}）…"
  "$PYTHON" -m flask run --host 127.0.0.1 --port "$FLASK_PORT" --with-threads \
    >>"$RUN_DIR/flask.log" 2>&1 &
FLASK_PID=$!

flask_ready=0
for _ in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")"
  if [[ "$code" == "200" ]]; then
    flask_ready=1
    break
  fi
  if ! kill -0 "$FLASK_PID" 2>/dev/null; then
    echo "错误: Flask 进程意外退出。日志: $RUN_DIR/flask.log" >&2
    tail -20 "$RUN_DIR/flask.log" >&2 || true
    exit 1
  fi
  sleep 0.5
done
if [[ "$flask_ready" -ne 1 ]]; then
  echo "错误: Flask health 在 30s 内未返回 200。" >&2
  exit 1
fi

if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  echo "正在安装前端依赖 (npm install)…"
  (cd "$WEB_DIR" && npm install)
fi

cat <<EOF

HBM Demo 已启动
  Flask  : http://127.0.0.1:${FLASK_PORT}
  前端   : http://localhost:${VITE_PORT}
  Runner : 由大厅按需启动（在前端选/建故事后自动拉起）
按 Ctrl+C 停止全部进程

EOF

if command -v open >/dev/null 2>&1; then
  (sleep 2 && open "http://localhost:${VITE_PORT}") >/dev/null 2>&1 &
fi

{
  echo "RUNNER_PID=$RUNNER_PID"
  echo "FLASK_PID=$FLASK_PID"
  echo "FLASK_PORT=$FLASK_PORT"
} >"$PID_FILE"

cd "$WEB_DIR"
# Foreground Vite — Ctrl+C triggers trap → stop_demo.sh
npm run dev -- --host 127.0.0.1 --port "$VITE_PORT"
