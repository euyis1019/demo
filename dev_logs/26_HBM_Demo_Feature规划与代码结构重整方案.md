# 开发日志 26：HBM Demo Feature 规划与代码结构重整方案

**记录时间**：2026-05-24  
**分支**：`jensen-hwang-demo`  
**状态**：**规范定稿 · 结构迁移 M0 已落地**（本文档为后续重构的唯一依据）  
**依据来源**：
- 会议共识 → [`25_会议记录.md`](./25_会议记录.md)
- 目录与运行机制 → [`22_HBM_Demo目录结构与功能说明.md`](./22_HBM_Demo目录结构与功能说明.md)
- Agent 行为控制设计 → [`24_HBM_Demo_Agent行为控制整合方案.md`](./24_HBM_Demo_Agent行为控制整合方案.md)

---

## 1. 为什么要拆 Feature

### 1.1 会议与现状问题

| 问题 | 现状症状 | 目标 |
|------|----------|------|
| Flask 层堆叠 | `game_service.py` **1091 行**，Session / 打分 / inject / API2 / 读库混在一起 | 每个能力可独立描述、测试、PR |
| Feature 边界模糊 | 改 Turn 4 可能误触 Stats、改 UI 可能误触 routing | 改 A 不碰 B |
| 难以抽象提 PR | 「这周所有改动一起合」 | 每 1–2 天一个 Feature PR |
| Agent 抢戏 | 7 Agent 每 tick 全跑 LLM | ABCS 作为独立 Feature 族渐进落地 |

### 1.2 产品定位约束（所有 Feature 的前置验收）

Demo **不是传统游戏**，而是「轻量对话互动媒介」；每个 Feature 须说明：

1. **验证了什么引擎能力**（Tick / Agent / 总线 / IPC / 持久化）
2. **是否过度游戏化**（优先对话驱动 + 轻规则）
3. **能否独立开关或回滚**（配置开关或独立 PR revert）

终局形态：**Video Jam**（动态视频 + 气泡对话）。UI 类 Feature 与 Runner 类 Feature **必须分 PR**。

---

## 2. Feature 定义与命名规范

### 2.1 什么是 Feature

> **Feature** = 可命名、可验收、可独立合并的最小能力单元，在 Demo 中完成端到端闭环，且代码归属明确（见 §4 分层与 §5 目录）。

**不是 Feature**：「优化 game_service」「整理前端」——应拆成多个 Feature 或纯 refactor PR。

### 2.2 命名与提交

```
<type>(<scope>): <一句话能力>

type:  feat | fix | refactor | docs | chore
scope: f01_session | f05_routing | f07_abcs | web | runner | ipc
```

### 2.3 Feature 交付 Checklist（每个 Feature PR 必填）

- [ ] **问题 / 方案 / 验收** 各 1–3 句（可链本文档 §6 对应 Feature ID）
- [ ] **归属层**：L0 配置 / L1 Runner / L2 编排 / L3 HTTP·UI（见 §4）
- [ ] **改动文件列表** + **刻意未改文件**
- [ ] **验收步骤** 3–5 步（`start_demo.sh` → 具体操作 → 期望现象）
- [ ] **不破坏四节点**：Turn 4 / 12 / 16 / 25（或显式标注为剧情 Feature 并更新 [`19`](./19_HBM_Demo_25轮参考台词.md)）
- [ ] **无密钥进库**（仅 `.env.example`）

### 2.4 Git 分支策略

| 分支 | 用途 |
|------|------|
| `main` | 仅 Initial commit，**禁止** Demo 直接推送 |
| `jensen-hwang-demo` | 全部 Demo 开发；Feature PR 合并目标 |

**节奏**：每 1–2 天提炼一个 Feature → 足够抽象则开 PR；仍耦合则先按 §7 迁移计划拆分再 PR。

---

## 3. 四层架构（Feature 写在哪一层）

```text
┌─────────────────────────────────────────────────────────────┐
│ L0 配置层（声明式，无业务逻辑）                                 │
│   hbm_scenario.yaml / turn_control.yaml / .env               │
├─────────────────────────────────────────────────────────────┤
│ L1 Runner 引擎层（写 world.db、跑 tick、Agent LLM）            │
│   core/runner/*  — kernel, world_step, hbm_agent, seed, ipc  │
├─────────────────────────────────────────────────────────────┤
│ L2 Demo 编排层（回合制规则，不直接碰 HTTP）                     │
│   features/f01–f07 — session, stats, routing, turn_context…  │
├─────────────────────────────────────────────────────────────┤
│ L3 传输与展示层（薄）                                          │
│   http/*, routes.py, web/src/*                               │
└─────────────────────────────────────────────────────────────┘
```

**硬规则**：

- `routes.py`：参数解析 + 委托 service + 错误映射（≤20 行业务逻辑）
- `game_service.py`（迁移后）：**仅** API1/API2 编排入口，不膨胀
- Agent 工具 / tick 白名单 / MOVE 拦截：**L1 + f07**，禁止在 Flask handler 里 if/else

---

## 4. 当前代码 → Feature 拆分（完整清单）

基于 2026-05-24 对 `agent_world/hbm_demo/` 全量阅读（20 个 Python 模块 ~2973 行；前端 37 文件 ~2280 行）。

### 4.1 Feature 总览

| ID | 名称 | 状态 | 目录（目标） | 核心职责 |
|----|------|------|--------------|----------|
| **F00** | 平台核心 Runner | ✅ 已实现 | `core/runner/` | 仿真内核装配、IPC 命令处理、world 初始化 |
| **F01** | 会话与重开 | ✅ 已实现 | `features/f01_session/` | HbmSession、Flask session CRUD、`RESET_WORLD` |
| **F02** | 玩家回合 API1 | ✅ 已实现 | `features/f02_player_turn/` | `handle_player_turn`、PendingTask、inject 编排 |
| **F03** | 动作结果 API2 | ✅ 已实现 | `features/f03_action_result/` | `get_action_result`、完成判定、消息格式化 |
| **F04** | 数值与打分 | ✅ 已实现 | `features/f04_stats/` | LLM/heuristic 打分、Stats 更新、immediate_msg |
| **F05** | 剧情路由 | ✅ 已实现 | `features/f05_story_routing/` | Phase 节点 A/B/C/D、inject 目标、Turn 16/25 |
| **F06** | 只读世界模型 | ✅ 已实现 | `features/f06_read_model/` | `ReadOnlyWorldDB`、F2F/RDC/GRP 查询 |
| **F07** | Agent 行为控制 ABCS | 📋 设计稿 | `features/f07_agent_control/` | turn_control、turn_context、L3/L5 |
| **F08** | HTTP 传输 | ✅ 已实现 | `http/` | Blueprint、health、ipc 客户端、错误映射 |
| **F09** | 前端三屏 UI | ✅ 已实现 | `web/src/features/` | 按屏/流程拆子 Feature（见 §4.3） |
| **F10** | 运维与启动 | ✅ 已实现 | `scripts/` | 一行启动、端口、stop |

### 4.2 后端：现有文件 → Feature 映射

| 现有文件 | 行数 | 归属 Feature | 迁移后路径 |
|----------|------|--------------|------------|
| `run_hbm.py` | 137 | F00 | `core/runner/run_hbm.py`（根保留 shim 入口） |
| `kernel.py` | 378 | F00 | `core/runner/kernel.py` |
| `world_step.py` | 73 | F00 + F07(L3) | `core/runner/world_step.py` |
| `hbm_agent.py` | 156 | F00 + F07(L5) | `core/runner/hbm_agent.py` |
| `seed.py` | 92 | F00 | `core/runner/seed.py` |
| `ipc_handlers.py` | 220 | F00 | `core/runner/ipc_handlers.py` |
| `broadcast_helper.py` | 35 | F00 | `core/runner/broadcast_helper.py` |
| `world_reset.py` | 81 | F01 | `features/f01_session/world_reset.py` ✅ M0 |
| `game_service.py` L77–112 | — | F01 | `features/f01_session/models.py` |
| `game_service.py` L417–499 | — | F01 | `features/f01_session/lifecycle.py` |
| `game_service.py` L431–468 | — | F01 | `features/f01_session/reset.py` |
| `game_service.py` L768–931 | — | F02 | `features/f02_player_turn/handler.py` |
| `game_service.py` L113–145,536–559 | — | F02 | `features/f02_player_turn/task.py` |
| `game_service.py` L1005–1091 | — | F03 | `features/f03_action_result/handler.py` |
| `game_service.py` L932–1004 | — | F03 | `features/f03_action_result/completion.py` |
| `game_service.py` L413–687 | — | F04 | `features/f04_stats/scoring.py` |
| `game_service.py` L608–622 | — | F04 | `features/f04_stats/deltas.py` |
| `routing.py` | 300 | F05 | `features/f05_story_routing/routing.py` ✅ M0 |
| `game_service.py` L208–407 | — | F06 | `features/f06_read_model/world_db.py` |
| `turn_control.yaml` | — | F07 | `features/f07_agent_control/turn_control.yaml`（待建） |
| `turn_context.py` | — | F07 | `features/f07_agent_control/turn_context.py`（待建） |
| `routes.py` | 205 | F08 | `http/routes.py` |
| `ipc_helper.py` | 76 | F08 | `http/ipc_helper.py` |
| `health.py` | 37 | F08 | `http/health.py` |
| `http_errors.py` | 18 | F08 | `http/http_errors.py` |
| `env_status.py` | 76 | 共享 | `shared/env_status.py` |
| `settings.py` | 32 | 共享 | `shared/settings.py` |
| `errors.py` | 33 | 共享 | `shared/errors.py` |
| `config_loader.py` | 16 | 共享 | `shared/config_loader.py` |
| `hbm_scenario.yaml` | 199 | L0 | 根目录（不变） |

**`game_service.py` 拆分后根文件职责**（目标 ~80 行）：

```python
# game_service.py — 兼容层 + 编排入口
from .features.f01_session import ...
from .features.f02_player_turn import handle_player_turn
from .features.f03_action_result import get_action_result
# re-export 供 routes.py / health.py 使用
```

### 4.3 前端 Feature 拆分

| ID | 名称 | 目录（目标） | 现有文件 |
|----|------|--------------|----------|
| F09a | 启动与恢复 | `web/src/features/boot/` | `BootScreen`, `useHealthCheck` |
| F09b | 主游戏循环 | `web/src/features/game-loop/` | `useGameLoop`, `useGameLoop.resetDemo` |
| F09c | 三栏布局 | `web/src/features/layout/` | `ThreeColumnLayout`, `StatusPanel` |
| F09d | 中屏 F2F | `web/src/features/main-chat/` | `MainChat`, `PlayerInput`, `MessageBubble` |
| F09e | 右栏 Observer | `web/src/features/observer/` | `ObserverPanel` |
| F09f | 结局流 | `web/src/features/endings/` | `GameOverScreen`, `EndingScreen`, `PhaseToast` |
| F09g | API 客户端 | `web/src/api/` | 保持现状（已是薄层） |
| F09h | 全局状态 | `web/src/store/` | `gameStore`（后续可按 feature 拆 slice） |

前端迁移 **不影响** 后端契约；`web/src/api/types.ts` 与 `routes.py` 对齐即可。

### 4.4 引擎依赖（不可移入 hbm_demo 的部分）

| 引擎路径 | 使用者 | 说明 |
|----------|--------|------|
| `demo/demo_agent.py` | F00 `hbm_agent` | 继承 DemoAgent，**不修改 demo/** |
| `ipc/commands.py` | F00, F08 | 新 IPC 命令一个 Feature 一个 PR |
| `app/services/simulation_ipc.py` | F08 | Flask → Runner 客户端 |
| `world/*`, `buses/*`, `script/*`, `memory/*`, `persistence/*` | F00 | 引擎核心，Demo 只装配 |

---

## 5. 目标目录结构（重整后）

```text
agent_world/hbm_demo/
├── __init__.py                    # 包说明 + FEATURE_REGISTRY
├── hbm_scenario.yaml              # L0 场景
├── turn_control.yaml              # L0 F07（待建）
│
├── run_hbm.py                     # 入口 shim → core.runner.run_hbm
├── routes.py                      # 入口 shim → http.routes
├── game_service.py                # 兼容 re-export（迁移完成后 ~80 行）
├── routing.py                     # 兼容 shim → features.f05_story_routing
├── world_reset.py                 # 兼容 shim → features.f01_session
│
├── shared/                        # 跨 Feature 基础设施
│   ├── env_status.py
│   ├── settings.py
│   ├── errors.py
│   └── config_loader.py
│
├── core/
│   └── runner/                    # F00 平台核心
│       ├── run_hbm.py
│       ├── kernel.py
│       ├── world_step.py
│       ├── hbm_agent.py
│       ├── seed.py
│       ├── ipc_handlers.py
│       └── broadcast_helper.py
│
├── features/
│   ├── __init__.py                # FEATURE_REGISTRY + 文档索引
│   ├── f01_session/               # 会话与重开
│   │   ├── models.py              # HbmSession
│   │   ├── lifecycle.py           # create/load/save
│   │   ├── reset.py               # reset_demo (Flask)
│   │   └── world_reset.py         # reset_world_runtime (Runner)
│   ├── f02_player_turn/           # API 1
│   │   ├── task.py                # PendingTask
│   │   └── handler.py             # handle_player_turn
│   ├── f03_action_result/         # API 2
│   │   ├── completion.py
│   │   └── handler.py
│   ├── f04_stats/                 # 数值双轨（明线）
│   │   ├── scoring.py
│   │   └── deltas.py
│   ├── f05_story_routing/         # 剧情节点
│   │   └── routing.py
│   ├── f06_read_model/            # 只读 DB
│   │   └── world_db.py
│   └── f07_agent_control/         # ABCS（待实现）
│       ├── turn_control.yaml
│       ├── turn_context.py
│       └── tool_guard.py          # L5 工具/MOVE 拦截
│
├── http/                          # F08 HTTP 薄层
│   ├── routes.py
│   ├── ipc_helper.py
│   ├── health.py
│   └── http_errors.py
│
├── scripts/                       # F10
├── sim/                           # 运行时产物
└── web/                           # F09 前端
    └── src/
        ├── api/
        ├── store/
        └── features/              # 按 F09a–h 渐进迁移
            ├── boot/
            ├── game-loop/
            ├── layout/
            ├── main-chat/
            ├── observer/
            └── endings/
```

### 5.1 是否每个 Feature 单独建文件夹？

**是，但有规则：**

| 规则 | 说明 |
|------|------|
| **一 Feature 一目录** | 目录名 `fNN_snake_case`，与 §4.1 ID 对齐 |
| **共享不放 Feature 里** | `shared/`、`core/runner/` 是平台层，不是业务 Feature |
| **兼容 shim 保留在根** | 根目录 `routing.py` 等 re-export，避免一次性改 20+ import |
| **配置放 L0 根或 Feature 内** | 场景 yaml 在根；`turn_control.yaml` 属 F07 放 `features/f07_agent_control/` |
| **入口脚本路径不变** | `python -m agent_world.hbm_demo.run_hbm` 永远有效 |
| **Flask Blueprint 注册不变** | `app/__init__.py` 仍 `from agent_world.hbm_demo.routes import hbm_bp` |

### 5.2 Feature 间依赖规则（禁止环）

```text
L3 http ──► L2 features ──► L1 core/runner ──► agent_world 引擎
                │                    │
                └──── shared ◄───────┘

允许：f02 → f04, f05, f06, f08(ipc)
允许：f05 → f08(ipc), shared, core(resolve_api_key)
禁止：core/runner → features/* （Runner 不得依赖 Flask Feature）
禁止：f06 → f02 （读模型不得依赖 API 编排）
```

---

## 6. 各 Feature 详细规格

### F00 — 平台核心 Runner

**职责**：双进程中的 Runner 侧；装配 WorldEngine、HbmAgent×7、IPC、tick 推进。

**边界**：不知道 Flask Session、不知道 Phase 节点判定（仅执行 inject payload）。

**验收**：`run_hbm` 启动 → `env_status.status=running` → IPC `LIST_PLACES` 可用。

**后续 F07 扩展点**：`world_step.set_tick_context()`、`hbm_agent` 工具过滤。

---

### F01 — 会话与重开

**职责**：
- `HbmSession` 数据模型（place_id / phase / player_turn / stats）
- Flask session 持久化
- `POST session/reset` → IPC `RESET_WORLD` → 清 world.db + 重 seed

**关键文件**：`features/f01_session/*`，Runner 侧 `world_reset.py`。

**验收**：
1. `session/start` → turn=1, Phase 1
2. 玩 2 轮后点「重开」→ turn=1，消息清空，tick 归零

**会议关联**：双轨数值的 **Session 权威**（place_id/phase 以 session 为准，见 [`17`](./17_HBM_Demo实现注意事项.md) §3）。

---

### F02 — 玩家回合（API 1）

**职责**：`handle_player_turn` 主编排：

```text
score (F04) → immediate_msg (F04) → build_inject (F05) → IPC inject (F08)
→ apply_routing (F05) → save session/task
```

**边界**：不直接 SQL；不解析 HTTP。

**验收**：Turn 1 发言 → 返回 task_id + immediate_msg；Runner 日志有 inject。

---

### F03 — 动作结果（API 2）

**职责**：轮询 `env_status.current_tick` + `ReadOnlyWorldDB` → 返回 F2F/RDC/GRP + stats_update。

**关键逻辑**：`check_action_complete`（Phase 1：RDC(1→2) 或 F2F 或 tick 超时）。

**验收**：API 2 `status=completed` 时中屏/右栏消息符合 Phase。

---

### F04 — 数值与打分（明线 + 暗线）

**职责**：
- **明线**：vision / execution / trust / burnout → 前端 StatusPanel
- **暗线**（规划）：隐藏变量推动故事，不可见；单独字段，不进 yaml soul

**实现**：LLM JSON 打分 + heuristic 兜底；`apply_stat_deltas`。

**会议关联**：「数值驱动」与「纯对话驱动」双轨；明线 UI 可见，暗线仅 debug 可观测。

**验收**：发言后 stats 变化；Turn 4 低分触发 Bad End（F05 节点 A）。

---

### F05 — 剧情路由

**职责**：
- `PHASE_INJECT_AGENTS` — 每 Phase inject 目标
- 节点 A Turn 4 / B Turn 12 / C Turn 20 / D Turn 25
- Turn 16 AMD 广播 + Sam 搅局
- Turn 25 意图分类 → ending_id

**边界**：不做 Stats 计算（读 session.stats）；通过 IPC 发 MOVE / inject。

**验收**：见 [`19`](./19_HBM_Demo_25轮参考台词.md) Turn 4/12/16/25 人工清单。

---

### F06 — 只读世界模型

**职责**：`ReadOnlyWorldDB` — Flask 侧只读 SQLite；F2F/RDC/GRP 格式化；`sender_id=-1` → 「彭博终端」。

**边界**：只读；WAL 未启用时带 timeout 重试（见 [`17`](./17) §2）。

---

### F07 — Agent 行为控制 ABCS（待实现）

**职责**：实现 [`24`](./24_HBM_Demo_Agent行为控制整合方案.md) 五层栈 L1–L5。

**子阶段**：

| 子 PR | 内容 | 验收 |
|-------|------|------|
| F07-A | temperature + turn_context 骨架 + L4 约束前缀 | Phase 1 GRP 下降 |
| F07-B | L3 tick 白名单 + L5 工具/MOVE 拦截 | Runner 日志仅 Agent 1 |
| F07-C | Turn hint 字典 + 回归脚本 | Turn 1–4、16 无抢戏 |

**配置开关**：`turn_control.yaml` → `enabled: false` 可回滚。

**会议关联**：Agent 边界拒绝、去 AI 味（L1+L2 独立小 PR）。

---

### F08 — HTTP 传输

**职责**：Blueprint 7 端点；IPC 客户端；health 栈检查；错误 JSON。

**边界**：零业务规则；全部委托 F01–F03。

---

### F09 — 前端三屏 UI

**职责**：Boot → 三栏 → 轮询 → 结局；`resetDemo` 调 F01 reset API。

**子 Feature 独立 PR**：如 F09c 仅改 StatusPanel 样式，不碰 game-loop。

---

### F10 — 运维与启动

**职责**：`start_demo.sh` / `stop_demo.sh` / 端口探测。

**约束**：脚本引用的 Python 模块路径在迁移期间**不得改变** `-m agent_world.hbm_demo.run_hbm`。

---

## 7. 迁移路线图（保证 Demo 始终可运行）

### 原则

1. **Strangler Fig**：新目录逐步接管，根目录 shim re-export，旧 import 路径不失效
2. **一个迁移 PR = 一个 Feature 或一层目录**，每步 `start_demo.sh` 验收
3. **先拆 game_service，后动 core/runner，最后动 web/features**

### 阶段

| 阶段 | 内容 | 风险 | 验收 |
|------|------|------|------|
| **M0** ✅ | 建 `features/`、`shared/` 骨架；`routing`、`world_reset` 迁入 + 根 shim | 低 | import 正常；Turn 1 E2E |
| **M1** ✅ | `shared/*` 四文件迁入；根 shim | 低 | health + session/start |
| **M2** ✅ | 拆 `game_service` → f01–f04、f06；根 `game_service` re-export | 中 | 完整 25 轮可玩 |
| **M3** ✅ | `core/runner/*` 迁入；`run_hbm` shim | 中 | Runner IPC 全命令 |
| **M4** ✅ | `http/*` 迁入；`routes` shim | 低 | 7 HTTP 端点 |
| **M5** ✅ | 实现 F07 ABCS Phase A→C | 中 | §24 验收清单 |
| **M6** ✅ | 前端 `web/src/features/*` | 低 | UI 无回归 |

### M6 已落地文件

```
web/src/features/
├── index.ts              # FEATURE_REGISTRY F09a–h
├── boot/                 # F09a BootScreen, useHealthCheck, RunnerNotReadyModal
├── game-loop/            # F09b useGameLoop, LoadingOverlay, useLoadingElapsed
├── layout/               # F09c ThreeColumnLayout, StatusPanel
├── main-chat/            # F09d MainChat, PlayerInput, MessageBubble
├── observer/             # F09e ObserverPanel, useEnvStatus
├── endings/              # F09f GameOverScreen, EndingScreen, PhaseToast
└── shared/               # useAutoScroll
web/src/components/*.tsx  # 根 shim → features/*
web/src/hooks/*.ts        # 根 shim → features/*
```

### M5 已落地文件

```
turn_control.yaml
features/f07_agent_control/config.py, matrix.py, turn_context.py, tool_guard.py
turn_context.py                                    # 根 shim
core/runner/world_step.py                          # L3 _pick_active
core/runner/hbm_agent.py                           # L2/L5
core/runner/ipc_handlers.py                        # turn_context IPC
http/ipc_helper.py                                 # payload turn_context
features/f05_story_routing/routing.py              # L4 约束前缀
hbm_scenario.yaml                                  # L1/L2 temperature + soul
```

### M4 已落地文件

```
http/routes.py, ipc_helper.py, health.py, http_errors.py
routes.py, ipc_helper.py, health.py, http_errors.py   # 根 shim
```

### M3 已落地文件

```
core/runner/run_hbm.py, kernel.py, hbm_agent.py, world_step.py
core/runner/seed.py, ipc_handlers.py, broadcast_helper.py
run_hbm.py, kernel.py, hbm_agent.py, …   # 根 shim
```

### M2 已落地文件

```
features/f01_session/models.py, paths.py, lifecycle.py, reset.py, logging.py, constants.py
features/f02_player_turn/handler.py, task.py, inject.py
features/f03_action_result/handler.py, completion.py
features/f04_stats/scoring.py, deltas.py
features/f06_read_model/world_db.py
game_service.py                 # 根 shim (~100 行 re-export)
```

### M1 已落地文件

```
shared/env_status.py
shared/settings.py
shared/errors.py
shared/config_loader.py
shared/__init__.py              # 统一 re-export
env_status.py / settings.py / errors.py / config_loader.py  # 根 shim
```

### M0 已落地文件

```
features/__init__.py          # FEATURE_REGISTRY
features/f01_session/world_reset.py
features/f05_story_routing/routing.py
routing.py                    # shim
world_reset.py                # shim
```

### 每阶段回滚

Git revert 单 PR 即可；F07 额外用 `turn_control.enabled: false`。

---

## 8. 双轨剧情机制（Feature 协作）

```text
玩家输入
    │
    ├─ F04 明线打分 ──► session.stats ──► F09 StatusPanel
    ├─ F04 暗线（规划）──► 隐藏变量 ──► F05 节点判定
    ├─ F05 inject 目标 ──► F02 IPC ──► F00 tick
    └─ F07 约束（规划）──► TurnContext ──► F00 Agent 行为
```

| 轨道 | Feature | 用户可见 |
|------|---------|----------|
| 纯对话 | F02/F03/F00 | 中屏 F2F、右栏 RDC/GRP |
| 数值明线 | F04/F09 | 左栏四维 Stats |
| 数值暗线 | F04（扩展） | 不可见 |
| 阶段硬约束 | F05 + F07 | Phase Toast、地点切换 |

---

## 9. 反模式清单

| 反模式 | 正确归属 |
|--------|----------|
| 在 `routes.py` 写 SQL / IPC 细节 | F08 只委托 |
| 在 `game_service` 新增 Agent 工具逻辑 | F00/F07 |
| 在 yaml soul 堆 500 字阶段规则 | F07 L4 turn_context |
| 7 Agent 每 tick 全跑 LLM | F07 L3 |
| 一个 PR 含 F05 改节点 + F09 改 UI + F07 | 拆 3 个 PR |
| Feature 目录互相 import 成环 | 遵守 §5.2 |

---

## 10. 待办 Feature  backlog（优先级）

| 优先级 | Feature | 说明 |
|--------|---------|------|
| P0 | M2 game_service 拆分 | 解除 1091 行上帝对象 |
| P0 | F07-B L3 tick 白名单 | Phase 1 抢戏根因 |
| P1 | F07-A L4 约束前缀 | 快速见效 |
| P1 | F07 恶意输入边界 | 会议待办 |
| P2 | F04 暗线数值 | 沉浸感 |
| P2 | F09 Galgame UI | 会议待办，独立 PR |
| P3 | M6 前端 features 目录 | 体验类 |
| P3 | F07-C E2E 回归脚本 | 自动化 |

---

## 11. 关联文档索引

| 文档 | 关系 |
|------|------|
| [`25_会议记录.md`](./25_会议记录.md) | 分支策略、Feature 提炼节奏、Flask 瘦身 |
| [`24_ABCS`](./24_HBM_Demo_Agent行为控制整合方案.md) | F07 详细设计 |
| [`22_目录结构`](./22_HBM_Demo目录结构与功能说明.md) | 运行时总览；待 M2 后更新 §2 目录树 |
| [`23_启动重置`](./23_HBM_Demo启动重置与运行指南.md) | 每阶段验收命令 |
| [`17_注意事项`](./17_HBM_Demo实现注意事项.md) | Session 权威、SQLite 并发 |

---

## 12. 一句话原则

> **Demo 可以实验，但每个实验是一个有名字、有目录、有验收的 Feature；Flask 只传话，Runner 长肌肉，game_service 不再膨胀。**

---

*文档版本 v1.0 · M0 结构已落地 · 下一步：M1 shared 迁移 → M2 game_service 拆分 → F07-A 首个行为控制 PR*

---

## 13. M0 验收测试记录

**执行时间**：2026-05-24  
**脚本**：`agent_world/hbm_demo/scripts/test_m0_acceptance.py`  
**结果**：**ALL M0 TESTS PASSED**（约 65s）

| 用例 | 覆盖 Feature | 结果 |
|------|--------------|------|
| T1 静态 import + FEATURE_REGISTRY | F00–F10 注册表、F01/F05 shim | ✓ |
| T2 F05 routing 单元 | Phase 1 inject [1]、Turn 16 广播+Sam、节点 A 阈值 | ✓ |
| T3 Runner 入口 | F00 `python -m agent_world.hbm_demo.run_hbm` | ✓ |
| T4 E2E Turn 1 | F08 health、F02 player-turn、F03 action-result | ✓ |
| T5 session/reset | F01 重开 → tick=0、重开后完整回合 | ✓ |
| T6 前端构建 | F09 `npm run build` | ✓ |

**运行方式**（仓库根目录）：

```bash
./agent_world/hbm_demo/scripts/stop_demo.sh   # 可选，避免端口冲突
python agent_world/hbm_demo/scripts/test_m0_acceptance.py
```

脚本会自动启动 Runner + Flask（不启动 Vite），跑完 E2E 后清理进程。

---

## 14. M1 验收测试记录

**执行时间**：2026-05-24  
**脚本**：`agent_world/hbm_demo/scripts/test_m0_acceptance.py`（含 T1b M1 shared shim）  
**结果**：**ALL M0+M1 TESTS PASSED**

| 用例 | 覆盖 | 结果 |
|------|------|------|
| T1b shared 四模块 shim | env_status / settings / errors / config_loader | ✓ |
| T1b shared.load_scenario | config_loader 读 hbm_scenario.yaml | ✓ |
| T4 health + session/start | 依赖 shared.env_status、shared.errors | ✓ |
| T0–T6 全量回归 | M0 用例无回归 | ✓ |

**下一步**：M3 迁入 `core/runner/`。

---

## 15. M2 验收测试记录

**执行时间**：2026-05-24  
**脚本**：`agent_world/hbm_demo/scripts/test_m0_acceptance.py`（含 T1c M2 game_service shim）  
**结果**：**ALL M0+M1+M2 TESTS PASSED**

| 用例 | 覆盖 Feature | 结果 |
|------|--------------|------|
| T1c game_service shim | F01–F04、F06 与 features 同一实现 | ✓ |
| T1c shim 体积 | `game_service.py` ≤120 行 | ✓ |
| T4–T5 E2E | F02 handle_player_turn、F03 get_action_result、F01 reset | ✓ |
| T0–T6 全量回归 | M0/M1 无回归 | ✓ |

**下一步**：M4 迁入 `http/`。

---

## 16. M3 验收测试记录

**执行时间**：2026-05-24  
**脚本**：`agent_world/hbm_demo/scripts/test_m0_acceptance.py`（含 T1d M3 runner shim）  
**结果**：**ALL M0–M3 TESTS PASSED**

| 用例 | 覆盖 Feature | 结果 |
|------|--------------|------|
| T1d core/runner shim | build_kernel、resolve_api_key、wire_handlers、HbmAgent、main | ✓ |
| T1d IPC 命令 | INJECT、LIST_PLACES、MOVE、RESET_WORLD、CLOSE_ENV | ✓ |
| T4–T5 E2E | 含 INJECT + RESET_WORLD IPC | ✓ |
| T0–T6 全量回归 | M0–M2 无回归 | ✓ |

**下一步**：M4 `http/` 迁移。

---

## 17. M4 验收测试记录

**执行时间**：2026-05-24  
**脚本**：`agent_world/hbm_demo/scripts/test_m0_acceptance.py`（含 T1e M4 http shim）  
**结果**：**ALL M0–M4 TESTS PASSED**

| 用例 | 覆盖 Feature | 结果 |
|------|--------------|------|
| T1e http shim | routes、ipc_helper、health、http_errors | ✓ |
| T1e hbm_bp | 8 个 HTTP 端点注册 | ✓ |
| T4 GET /session | F08 会话快照 | ✓ |
| T0–T6 全量回归 | M0–M3 无回归 | ✓ |

**修复**：`http/__init__.py` 不再 eager import `routes`，避免 `ipc_helper` → `routes` → `game_service` → `reset` 循环依赖。

**下一步**：M6 前端 `web/src/features/` 拆分。

---

## 18. M5 验收测试记录

**执行时间**：2026-05-24  
**脚本**：`agent_world/hbm_demo/scripts/test_m0_acceptance.py`（含 T1f M5 F07 ABCS）  
**结果**：**ALL M0–M5 TESTS PASSED**

| 用例 | 覆盖 Feature | 结果 |
|------|--------------|------|
| T1f F07 单元 | turn_context、matrix、tool_guard、根 shim | ✓ |
| T2 L4 前缀 | inject payload 含「系统约束」 | ✓ |
| T4 E2E GRP=0 | Phase 1 Turn 1 无 CEO 群聊（干净 world.db） | ✓ |
| T1f F03 ipc_end | 6-tick inject 结束后 action-result 不卡 processing | ✓ |
| T5 session/reset | 重开后 Turn 1 仍通过 | ✓ |
| T0–T6 全量回归 | M0–M4 无回归 | ✓ |

**ABCS 五层**：L1 soul 服从句 + L2 temperature 0.65 + L3 tick 白名单 + L4 约束前缀 + L5 工具/MOVE 拦截。回滚：`turn_control.yaml` → `enabled: false`。

**复测修复（2026-05-24）**：F03 `check_action_complete` 在 `ipc_end_tick` 到达时完成轮询，避免 6-tick inject 后无 LLM 消息时永久 `processing`。

**下一步**：M6 前端 features 目录。

---

## 19. M6 验收测试记录

**执行时间**：2026-05-24  
**脚本**：`agent_world/hbm_demo/scripts/test_m0_acceptance.py`（含 T1g M6 前端 features）  
**结果**：**ALL M0–M6 TESTS PASSED**

| 用例 | 覆盖 Feature | 结果 |
|------|--------------|------|
| T1g features 目录 | F09a–f + shared 七目录 | ✓ |
| T1g shim | components/BootScreen、hooks/useGameLoop → features | ✓ |
| T6 npm run build | TypeScript + Vite 无回归 | ✓ |
| T4–T5 E2E | 后端全链路无回归 | ✓ |

**结构**：Strangler Fig — `App.tsx` 仍从 `./components` / `./hooks` 导入，实现位于 `web/src/features/`。

**里程碑**：M0–M6 Feature 化重整全部完成。

