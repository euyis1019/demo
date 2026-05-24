# 开发日志 22：HBM Demo 目录结构与功能说明

**记录时间**：2026-05-23  
**分支**：`jensen-hwang-demo`  
**应用目录**：`agent_world/hbm_demo/`  
**关联文档**：
- 后端开发规划 → [`20_HBM_Demo开发规划_PLAN.md`](./20_HBM_Demo开发规划_PLAN.md)
- 前端 + 一键启动规划 → [`21_HBM_Demo后续开发规划_PLAN2.md`](./21_HBM_Demo后续开发规划_PLAN2.md)
- 完成度归档 → [`18_HBM_Demo后端Phase0-6完成与后续待办.md`](./18_HBM_Demo后端Phase0-6完成与后续待办.md)
- **启动 / 重置 / 运行** → [`23_HBM_Demo启动重置与运行指南.md`](./23_HBM_Demo启动重置与运行指南.md)
- **Agent 行为控制（设计）** → [`24_HBM_Demo_Agent行为控制整合方案.md`](./24_HBM_Demo_Agent行为控制整合方案.md)

> 原位于 `agent_world/hbm_demo/PLAN.md`、`PLAN2.md` 的两份开发规划已迁入 `dev_logs/20`、`dev_logs/21`；应用目录仅保留可运行代码与 README。

---

## 1. 运行时总览

Demo 采用**双进程 + 前端**架构：Flask 负责 HTTP / Session / 只读查库；Runner 子进程负责 LLM Agent、写 `world.db`、推进 tick。两者通过 IPC（Unix socket + JSON）通信，共用同一 `sim_dir`。

```text
浏览器 (5173)
    │  POST player-turn / GET action-result / GET env-status
    ▼
Flask — routes.py + game_service.py          ← Session、Stats、路由节点、只读 SQLite
    │  IPC: inject_batch / MOVE_AGENT
    ▼
run_hbm.py — kernel + WorldStep + HbmAgent   ← 写 world.db、env_status.json
    │
    ▼
sim/hbm_memory_war/world.db + ipc/ + env_status.json
```

**玩家 Turn 与 World Tick 的关系**：玩家每发一条台词触发一次 API 1（inject + 若干 tick）；API 2 轮询直到本回合 NPC 动作完成。无后台空转主循环（见 `dev_logs/17`）。

---

## 2. 后端目录树与职责

```text
agent_world/hbm_demo/
├── hbm_scenario.yaml      # 场景 YAML：地点、7 个 Agent、群、能力、prompt soul
├── run_hbm.py             # Runner 入口：argparse、IPCServer、信号处理
├── kernel.py              # 装配 WorldEngine、三总线、HbmAgent、inject handler
├── seed.py                # 首次启动写入 world.db 初始状态
├── config_loader.py       # 加载并校验 hbm_scenario.yaml
├── hbm_agent.py           # LLM Agent（继承 DemoAgent，扩展 update_state / 关系工具）
├── world_step.py          # HbmWorldStep：同地点 Agent 并行 LLM
├── ipc_handlers.py        # Runner 侧 IPC 命令注册（inject、MOVE 等）
├── ipc_helper.py          # Flask 侧 IPC 客户端封装
├── broadcast_helper.py    # Runner 内系统广播（insert_message）
├── game_service.py        # 核心游戏逻辑：Session、Stats、API 1/2、WorldDB 查询、路由调用
├── routing.py             # 四 Phase 剧情节点 A/B/C/D、inject 目标、Turn 16 广播
├── routes.py              # Flask Blueprint `/api/hbm/simulations/<sim_id>/...`
├── env_status.py          # 读写 merge `env_status.json`（current_tick、status）
├── health.py              # GET /health：Runner + world.db 就绪探针
├── errors.py              # 自定义异常（RunnerNotReady、DatabaseReadError 等）
├── settings.py            # 超时、重试、默认 sim_dir 等常量
├── http_errors.py         # Flask 错误响应格式化
├── __init__.py            # 包说明
├── README.md              # 启动说明、API 速查、环境变量
├── .env.example           # API Key 示例
├── scripts/
│   ├── start_demo.sh      # 一行启动 Runner + Flask + Vite
│   ├── stop_demo.sh       # 清理三进程
│   └── demo_ports.sh      # 端口探测（5050–5059、5173）
├── sim/
│   └── hbm_memory_war/    # 运行时产物（world.db、ipc、env_status.json，gitignore）
└── web/                   # 前端（见 §3）
```

### 2.1 核心文件功能详解

| 文件 | 功能 |
|------|------|
| **`hbm_scenario.yaml`** | 定义地点（前台、谈判室、黄总私密室等）、Agent 1–7 的 soul / 长期目标 / 初始位置、群 100/200、signal_uplink 能力。 |
| **`run_hbm.py`** | 解析 `--config` / `--sim-dir`；调用 `build_kernel`；启动 `IPCServer`；写入 `env_status.json` 为 `running`。 |
| **`kernel.py`** | 创建 `WorldEngine`、三总线；为每个 Agent 实例化 `HbmAgent`；注册 inject handler：接收 Flask 注入的 `dialogue_injection` 事件后跑 N tick。 |
| **`hbm_agent.py`** | 封装 LLM 工具调用（`speak_to_local`、`send_message`、`send_to_group`、`request_move`、`update_state` 等）；处理 `scripted_notification` 与记忆更新。 |
| **`world_step.py`** | 重写 `_run_single_agent`：同地点多个 Agent 的 LLM 决策 `asyncio.gather` 并行。 |
| **`game_service.py`** | **API 1** `player_turn`：LLM 打分、`immediate_msg`、创建 `PendingTask`、inject batch、执行路由节点；**API 2** `get_action_result`：轮询 F2F/RDC/GRP、Stats 更新；Session 读写；`check_action_complete` 完成判定。 |
| **`routing.py`** | Phase 1–4 的 inject 目标 Agent 列表；节点 A（Turn 4 进 Phase 2 / Bad End）、B（Turn 12 Tech VP 正面 RDC）、C（Turn 20 进 Phase 4）、D（Turn 25 结局）；Turn 16 AMD 广播 + Sam 搅局。 |
| **`routes.py`** | HTTP 端点：`session/start`、`session`、`health`、`env-status`、`player-turn`、`action-result`、`debug-inject`。 |
| **`ipc_helper.py`** | `send_inject_batch`、`send_move_agent`；超时与错误映射。 |
| **`env_status.py`** | Runner 与 Flask 共享的轻量状态文件；前端底栏 `World Tick` 来源。 |

### 2.2 消息通道与三屏对应

| 通道 | DB `channel_type` | 写入方式 | 前端展示 |
|------|-------------------|----------|----------|
| 面对面 | `F2F` | Agent 调用 `speak_to_local` | **中屏 Main Chat**（`public_messages`） |
| 私聊 | `RDC` | Agent 调用 `send_message` | **右栏 Observer**（`observer_messages`） |
| 群聊 | `GRP` | Agent 调用 `send_to_group` | **右栏 Observer**（`group_messages`） |

中屏只显示 F2F（`public_messages`）。NPC 需在同地点调用 `speak_to_local` 才会出现在中屏；RDC/GRP 走右栏 Observer。

### 2.3 Flask 注册点

唯一引擎壳改动：`agent_world/app/__init__.py` 注册 `hbm_bp` Blueprint，前缀 `/api/hbm`。

---

## 3. 前端目录树与职责

```text
agent_world/hbm_demo/web/
├── index.html
├── package.json
├── vite.config.ts           # dev proxy → Flask 5050
├── src/
│   ├── main.tsx / App.tsx
│   ├── api/                 # HTTP 客户端与类型
│   │   ├── client.ts        # fetch 封装、cookie session
│   │   ├── hbm.ts           # 五端点：session/start、player-turn、action-result 等
│   │   ├── types.ts         # 请求/响应 TypeScript 类型
│   │   └── errors.ts        # 503/504 等错误类
│   ├── store/
│   │   ├── gameStore.ts     # 全局状态：messages、stats、phase、轮询 task_id
│   │   └── GameStoreProvider.tsx
│   ├── hooks/
│   │   ├── useGameLoop.ts   # API 1 → 轮询 API 2 主循环
│   │   ├── useEnvStatus.ts  # 底栏 World Tick 轮询
│   │   └── useHealthCheck.ts
│   ├── components/
│   │   ├── layout/ThreeColumnLayout.tsx   # 左 Stats / 中 Chat / 右 Observer
│   │   ├── MainChat.tsx       # 中屏 F2F + 玩家输入
│   │   ├── ObserverPanel.tsx  # RDC + GRP 分 Tab
│   │   ├── StatusPanel.tsx    # Vision / Execution / Trust / Burnout
│   │   ├── PlayerInput.tsx
│   │   ├── MessageBubble.tsx / MessageLine.tsx
│   │   ├── PhaseToast.tsx     # Phase 切换提示
│   │   ├── GameOverScreen.tsx / EndingScreen.tsx / BootScreen.tsx
│   │   └── RunnerNotReadyModal.tsx
│   ├── constants/           # phaseTransitions、gameLoop 轮询间隔、端口
│   └── utils/
│       ├── messages.ts      # 玩家气泡 attempted_at 排序（stampPlayerBubble）
│       └── places.ts        # place_id → 中文地点名
└── README.md
```

### 3.1 前端数据流

1. **BootScreen** → `POST session/start` → 进入三栏主界面  
2. 玩家输入 → `POST player-turn` → 显示 `immediate_msg` + 玩家气泡  
3. `useGameLoop` 轮询 `GET action-result?task_id=...`  
4. `status=completed` 时合并 `public_messages` / `observer_messages` / `stats_update`  
5. `env-status` 独立轮询更新底栏 tick  

---

## 4. 运行时产物（sim/）

| 路径 | 说明 |
|------|------|
| `sim/hbm_memory_war/world.db` | SQLite：Agent 位置、消息、时钟 tick |
| `sim/hbm_memory_war/env_status.json` | `current_tick`、`status`（running/stopped） |
| `sim/hbm_memory_war/ipc/` | Unix socket，Flask ↔ Runner |
| `scripts/.run/` | start_demo 日志（flask.log、runner.log） |

环境变量 `HBM_SIM_DIR` 可覆盖 sim 目录；未设置时默认使用仓库内 `sim/hbm_memory_war/`。

---

## 5. 四 Phase 剧情与关键 Turn

| Phase | 地点 | 玩家 Turn | 要点 |
|-------|------|-----------|------|
| Phase 1 | `nvidia_reception` 前台 | 1–3 | 前台 F2F + 向 Jensen RDC 汇报 |
| Phase 2 | `jensen_private_room` | 4–12 | Turn 4 需 vision+execution≥15；Turn 12 需 execution≥20 + Tech VP 正面 RDC |
| Phase 3 | `negotiation_room` | 13–20 | Turn 16 AMD 广播；多方 GRP/RDC 谈判 |
| Phase 4 | 谈判室延续 | 21–25 | Turn 25 结局 |

参考台词见 [`19_HBM_Demo_25轮参考台词.md`](./19_HBM_Demo_25轮参考台词.md)。

---

## 6. 开发规划文档归档说明

| 原路径 | 新路径 | 内容 |
|--------|--------|------|
| `agent_world/hbm_demo/PLAN.md` | `dev_logs/20_HBM_Demo开发规划_PLAN.md` | 后端 Phase 0–6 分阶段任务（**已完成**） |
| `agent_world/hbm_demo/PLAN2.md` | `dev_logs/21_HBM_Demo后续开发规划_PLAN2.md` | 前端 F0–F6 + 一行启动 + 验收（**已完成**） |

后续大改仅在 `jensen-hwang-demo` 分支进行；`main` 保持 Initial commit，Demo 相关规划与说明统一放在 `dev_logs/`。

---

## 7. 快速定位表（改什么找哪个文件）

| 想改… | 文件 |
|--------|------|
| NPC 性格 / 强制规则 | `hbm_scenario.yaml` |
| Agent 工具行为 | `hbm_agent.py` + 引擎 `demo/demo_agent.py` |
| API 接口 / HTTP 路由 | `routes.py` |
| 打分、Stats、完成判定 | `game_service.py` |
| Turn 4/12/20/25 分支 | `routing.py` |
| inject tick 数量 / 并行 | `kernel.py`、`ipc_handlers.py` |
| 三屏 UI / 轮询 | `web/src/hooks/useGameLoop.ts`、`gameStore.ts` |
| 一键启动 / 端口 | `scripts/start_demo.sh`、`demo_ports.sh` |
