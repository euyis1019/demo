# HBM 显存价格保卫战 — Web Demo

《HBM 显存价格保卫战》本地可玩 Demo：**Runner**（LLM Agent + 世界仿真）+ **Flask**（回合编排 + HTTP API）+ **React 前端**（三栏 UI）。

详细产品/剧情规范见仓库 `dev_docs/`；Feature 化架构见 [`dev_logs/26_HBM_Demo_Feature规划与代码结构重整方案.md`](../../dev_logs/26_HBM_Demo_Feature规划与代码结构重整方案.md)。

---

## 快速开始

在**仓库根目录**：

```bash
# 1. Python 依赖（首次）
pip install -e .

# 2. API Key
cp agent_world/hbm_demo/.env.example agent_world/hbm_demo/.env
# 编辑 .env：DMXAPI_KEY=sk-...

# 3. 一行启动 Runner + Flask + Vite
./agent_world/hbm_demo/scripts/start_demo.sh
```

浏览器打开 **http://localhost:5173**。按 **Ctrl+C** 停止；或执行 `./agent_world/hbm_demo/scripts/stop_demo.sh`。

**验收测试**（不启动长期 dev server，自动起停 Runner/Flask）：

```bash
python agent_world/hbm_demo/scripts/test_m0_acceptance.py
```

25 轮参考台词：[`dev_logs/19_HBM_Demo_25轮参考台词.md`](../../dev_logs/19_HBM_Demo_25轮参考台词.md)

---

## 运行时架构

```text
浏览器 (Vite :5173)
    │  POST player-turn / GET action-result / GET session …
    ▼
Flask  (agent_world.app + hbm_bp)     ← L3：HTTP、Flask Session、只读 world.db
    │  IPC: inject_batch / MOVE / RESET_WORLD
    ▼
Runner (python -m agent_world.hbm_demo.run_hbm)   ← L1：写 world.db、推进 tick、Agent LLM
    │
    ▼
sim/hbm_memory_war/   world.db · ipc/ · env_status.json
```

- 玩家每发一条台词 → **API 1**（打分 + DialogueInjection + 若干 world tick）→ **API 2** 轮询直到本回合 NPC 动作完成。
- **必须先有 Runner**，Flask 与 Runner 共用同一 `HBM_SIM_DIR`。

---

## 代码结构（四层 + Feature）

```text
agent_world/hbm_demo/
├── hbm_scenario.yaml      # L0 场景：地点、Agent soul、LLM、群聊
├── .env / .env.example    # L0 API Key（.env 不提交）
│
├── run_hbm.py             # 入口 shim → core/runner/run_hbm.py
├── routes.py              # 入口 shim → http/routes.py (hbm_bp)
├── game_service.py        # 入口 shim → re-export features/f01–f04、f06
│
├── shared/                # 跨 Feature 工具（配置加载、env_status、错误、超时）
├── core/runner/           # F00 平台 Runner（内核、Agent、IPC、tick）
├── features/              # F01–F06 业务编排（见下表）
├── http/                  # F08 HTTP 传输（Blueprint、health、IPC 客户端）
│
├── web/                   # F09 前端（src/features/ 按屏拆分）
├── scripts/               # F10 启动、停止、验收测试
└── sim/hbm_memory_war/    # 运行时产物（gitignore）
```

### 根目录三个 shim 为何保留

| 文件 | 指向 | 用途 |
|------|------|------|
| `run_hbm.py` | `core/runner/run_hbm.py` | `python -m agent_world.hbm_demo.run_hbm` |
| `routes.py` | `http/routes.hbm_bp` | `agent_world.app` 注册 Blueprint |
| `game_service.py` | `features/*` 聚合 export | 历史 import 路径、HTTP 层委托 |

业务逻辑均在 `features/`、`core/`、`http/`；根目录不再放置重复实现。

---

## Feature 说明（F00–F10）

后端注册表：`features/__init__.py` → `FEATURE_REGISTRY`。  
前端注册表：`web/src/features/index.ts`。

| ID | 名称 | 目录 | 职责 |
|----|------|------|------|
| **F00** | 平台 Runner | `core/runner/` | `build_kernel` 装配世界；`HbmAgent` LLM 决策；`HbmWorldStep` 并行 tick；`ipc_handlers` 处理 INJECT/MOVE/RESET；`seed` 初始化场景 |
| **F01** | 会话与重开 | `features/f01_session/` | `HbmSession`（stats/phase/turn/place）；Flask session CRUD；`reset_demo` + IPC `RESET_WORLD` |
| **F02** | 玩家回合 API1 | `features/f02_player_turn/` | `handle_player_turn`：打分 → inject → IPC tick → F05 路由副作用；`PendingTask` 供 API2 轮询 |
| **F03** | 动作结果 API2 | `features/f03_action_result/` | `get_action_result`：完成判定（F2F/RDC/GRP/tick 超时）；格式化中屏 F2F 与 Observer RDC/GRP |
| **F04** | 数值与打分 | `features/f04_stats/` | LLM/heuristic 四维 Stats；`immediate_msg` 即时反应文案 |
| **F05** | 剧情路由 | `features/f05_story_routing/` | Phase 节点 A/B/C/D；inject 目标；Turn 16 广播 + Sam；Turn 25 意图与结局 ID |
| **F06** | 只读世界模型 | `features/f06_read_model/` | `ReadOnlyWorldDB`：Flask 侧只读 SQLite，查 F2F/RDC/GRP |
| **F08** | HTTP 传输 | `http/` | `hbm_bp` 八个端点；`ipc_helper`；`health`；统一错误映射 502/503/504 |
| **F09** | 前端三屏 UI | `web/src/features/` | 见下节 |
| **F10** | 运维 | `scripts/` | `start_demo.sh`、`stop_demo.sh`、`test_m0_acceptance.py` |

### 前端子 Feature（F09a–h）

| ID | 目录 | 说明 |
|----|------|------|
| F09a | `features/boot/` | 启动屏、健康检查、Runner 503 弹窗 |
| F09b | `features/game-loop/` | 双阶段回合（player-turn → poll action-result）、Loading |
| F09c | `features/layout/` | 三栏布局、左侧 Stats / 进度 |
| F09d | `features/main-chat/` | 中屏 F2F 公开对话、玩家输入 |
| F09e | `features/observer/` | 右栏 RDC / GRP 私聊与群聊 |
| F09f | `features/endings/` | Bad End、Turn 25 结局、Phase 切换 Toast |
| F09g | `api/` | HTTP 客户端与类型 |
| F09h | `store/` | `gameStore` reducer + Context |

---

## 配置

### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DMXAPI_KEY` | — | DeepSeek 官方 Key（见 `hbm_scenario.yaml` 中 `llm.model`） |
| `HBM_SIM_DIR` | `sim/hbm_memory_war/` | 仿真目录 |
| `FLASK_RUN_PORT` | 5050–5059 自动选取 | Flask 端口 |
| `VITE_PORT` | 5173 | 前端 dev 端口 |
| `HBM_IPC_TIMEOUT` | 600 | IPC inject 超时（秒） |

完整列表见 `.env.example`。

### `hbm_scenario.yaml`

- 7 个 Agent、4 个地点、2 个群聊
- `llm`：`base_url`、`model`（当前 `deepseek-chat`）

### Agent 行为控制（ABCS）

**当前 Demo 未包含 ABCS 运行时实现**（原 `features/f07_agent_control/`、`turn_control.yaml` 已移除）。  
设计与后续重建方案见 [`dev_logs/24_HBM_Demo_Agent行为控制整合方案.md`](../../dev_logs/24_HBM_Demo_Agent行为控制整合方案.md)。

Inject 后每 tick 仍由引擎默认调度**全部 Agent**（`WorldStep.scheduler=None`）；阶段 inject 目标仍由 F05 `PHASE_INJECT_AGENTS` 按 Phase 限定。

---

## HTTP API

前缀：`/api/hbm/simulations/hbm_memory_war/`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `session/start` | 初始化 Flask session |
| GET | `session` | 当前 stats / phase / turn |
| POST | `session/reset` | 重开（IPC RESET + session 清零） |
| GET | `health` | Runner + world.db 就绪探针 |
| GET | `env-status` | Runner tick / status |
| POST | `player-turn` | API 1 |
| GET | `action-result?task_id=` | API 2 轮询 |
| POST | `debug-inject` | 调试 inject（跳过完整游戏逻辑） |

---

## 游戏流程（可玩范围）

| 阶段 | Turn | 说明 |
|------|------|------|
| Phase 1 | 1–4 | 前台接待；Turn 4 需 vision+execution≥15，否则 Bad End |
| Phase 2 | 5–12 | Jensen 私密审查；Turn 12 节点 B → Phase 3 |
| Phase 3 | 13–20 | 谈判室；Turn 16 AMD 广播 + Sam；Turn 20 节点 C → Phase 4 |
| Phase 4 | 21–25 | 终局；Turn 25 返回结局 ID |

单回合含多次 LLM 调用，墙钟约 **15–90 秒**（7 Agent 并行 tick 时可能更慢）。

---

## 手动分进程启动

```bash
# 终端 1 — Runner
python -m agent_world.hbm_demo.run_hbm \
  --config agent_world/hbm_demo/hbm_scenario.yaml \
  --sim-dir agent_world/hbm_demo/sim/hbm_memory_war/

# 终端 2 — Flask
export HBM_SIM_DIR=agent_world/hbm_demo/sim/hbm_memory_war/
export FLASK_APP=agent_world.app:create_app
flask run --host 127.0.0.1 --port 5050

# 终端 3 — 前端
cd agent_world/hbm_demo/web && npm run dev
```

---

## 相关文档

| 文档 | 内容 |
|------|------|
| [`dev_logs/26`](../../dev_logs/26_HBM_Demo_Feature规划与代码结构重整方案.md) | Feature 规划与 M0–M7 迁移 |
| [`dev_logs/22`](../../dev_logs/22_HBM_Demo目录结构与功能说明.md) | 历史目录说明（部分已过时，以本文为准） |
| [`dev_logs/23`](../../dev_logs/23_HBM_Demo启动重置与运行指南.md) | 启动 / 重置 / 排错 |
| [`dev_logs/24`](../../dev_logs/24_HBM_Demo_Agent行为控制整合方案.md) | ABCS 设计（待重建） |
| [`dev_logs/19`](../../dev_logs/19_HBM_Demo_25轮参考台词.md) | 25 轮试玩台词 |

---

## 维护说明

- **不要**在根目录新增业务 `.py`；新能力放入对应 `features/fXX_*` 或 `core/runner/`。
- Agent 行为边界：按 [`dev_logs/24`](../../dev_logs/24_HBM_Demo_Agent行为控制整合方案.md) 重建 ABCS 后再接入。
- 提交前运行 `python agent_world/hbm_demo/scripts/test_m0_acceptance.py` 与 `cd web && npm run build`。
