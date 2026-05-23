# HBM 显存价格保卫战 — Web Demo

《HBM 显存价格保卫战》双进程 Demo：`run_hbm`（Runner + LLM Agent）与 Flask（Stats / 路由 / API）。

技术规范见仓库根目录 `dev_docs/`，开发规划见本目录 `PLAN.md`。

## 架构

```text
[ 前端 / curl ]
       │  POST player-turn / GET action-result
       ▼
[ Flask — game_service + routes ]  ← 只读 world.db + IPC
       │
       ▼
[ run_hbm.py 子进程 ]  ← 写 world.db、推进 tick
```

**必须先启动 Runner，再启动 Flask**，且两者共用同一 `sim_dir`。

## 环境要求

- Python 3.10+
- 依赖：见仓库根目录 `pyproject.toml`（`uv sync` 或 `pip install -e .`）
- LLM API Key（Runner Agent + Flask 打分 / immediate_msg）

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HBM_SIM_DIR` | `agent_world/hbm_demo/sim/hbm_memory_war/` | 仿真目录（`world.db`、IPC、env_status） |
| `DMXAPI_KEY` | — | LLM API Key（也可写在 `hbm_demo/.env` 或 `demo/.env`） |
| `HBM_IPC_TIMEOUT` | `600` | IPC inject 超时（秒），超时返回 HTTP 504 |
| `HBM_MOVE_TIMEOUT` | `30` | IPC MOVE 超时（秒） |
| `HBM_DB_TIMEOUT` | `5.0` | Flask 只读 SQLite 连接超时 |
| `HBM_DB_READ_RETRIES` | `6` | API 2 读库 locked 时重试次数 |
| `HBM_IMMEDIATE_MSG_TIMEOUT` | `1.0` | immediate_msg LLM 超时（秒） |
| `FLASK_APP` | `agent_world.app:create_app` | Flask 入口 |

## 启动步骤

### 1. 配置 API Key

```bash
export DMXAPI_KEY=sk-your-key
# 或写入 agent_world/hbm_demo/.env：
# DMXAPI_KEY=sk-your-key
```

### 2. 启动 Runner（终端 1）

```bash
python -m agent_world.hbm_demo.run_hbm \
  --config agent_world/hbm_demo/hbm_scenario.yaml \
  --sim-dir agent_world/hbm_demo/sim/hbm_memory_war/
```

等待日志出现 `HBM runner ready`，且 `sim/hbm_memory_war/env_status.json` 中 `status` 为 `running`。

### 3. 启动 Flask（终端 2）

```bash
export HBM_SIM_DIR=agent_world/hbm_demo/sim/hbm_memory_war/
export FLASK_APP=agent_world.app:create_app
flask run --port 5000
```

## API 速查

前缀：`/api/hbm/simulations/hbm_memory_war/`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `session/start` | 初始化 session（stats / phase / place_id） |
| GET | `env-status` | 读取 Runner `env_status.json` |
| POST | `player-turn` | API 1：打分 + inject + 路由 |
| GET | `action-result?task_id=...` | API 2：轮询 NPC 消息 |
| POST | `debug-inject` | 调试 inject（跳过完整游戏逻辑） |

### 示例：Turn 1

```bash
# 初始化
curl -s -X POST http://127.0.0.1:5000/api/hbm/simulations/hbm_memory_war/session/start \
  -c cookies.txt

# API 1
curl -s -X POST http://127.0.0.1:5000/api/hbm/simulations/hbm_memory_war/player-turn \
  -b cookies.txt -H 'Content-Type: application/json' \
  -d '{"player_text":"我的算法能把显存消耗降低80%。"}'

# API 2（替换 task_id）
curl -s "http://127.0.0.1:5000/api/hbm/simulations/hbm_memory_war/action-result?task_id=task_xxx" \
  -b cookies.txt
```

## HTTP 错误码（Phase 5）

| 状态码 | 场景 |
|--------|------|
| 503 | Runner 未就绪、SQLite 读库持续 locked |
| 504 | IPC inject / MOVE 超时 |
| 502 | IPC 返回 failed |
| 404 | 未知 `task_id` |

## 日志

结构化日志前缀 `hbm`，包含 `task_id`、`phase`、`player_turn`、`start_tick`、`end_tick` 等字段，便于联调排查。

## 人工试玩建议（Phase 1→4）

1. Turn 1–3：前台接待（Phase 1，`nvidia_reception`）
2. Turn 4：累计 vision+execution≥15 进入 Phase 2，否则 Bad End
3. Turn 5–12：私密审查（Phase 2，仅 Jensen）；Turn 12 需 execution≥20 且 Tech VP 正面 RDC
4. Turn 13–20：谈判室群战（Phase 3）；Turn 16 触发 AMD 广播 + Sam 搅局
5. Turn 20：burnout<80 且 vision≥30 进入 Phase 4
6. Turn 25：结局（API 1 直接返回 `completed` + `ending_id`）

单回合 inject 含 LLM 决策，墙钟约 15–60 秒，属正常现象。

## 目录结构

```text
hbm_demo/
  run_hbm.py          Runner 入口
  kernel.py           内核装配 + PlaceMutation 桥接
  hbm_agent.py        LLM Agent
  game_service.py     Stats / 路由 / API 逻辑
  routing.py          节点 A/B/C/D
  routes.py           Flask Blueprint
  ipc_helper.py       IPC 封装
  errors.py / settings.py / http_errors.py
  hbm_scenario.yaml   场景配置
  sim/                运行时产物（world.db 等）
```
