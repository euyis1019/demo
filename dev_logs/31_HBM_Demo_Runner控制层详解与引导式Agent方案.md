# 开发日志 31：HBM Demo Agent 控制层 — 常驻世界 + 软引导方案（v2.0）

**记录时间**：2026-05-23（v2.0 重写）  
**状态**：**目标架构 + 实施规格**（分支 `feature/agent-control`）  
**取代**：v1.0 的「固定 inject 批 + F07-E 硬守卫」叙述；实施清单与 dev_logs/30 部分 PR 合并重排。

**前置文档**：

- [`dev_logs/30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md`](30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md) — Agent 原生输出、agent_driven 路由、F12 UI
- [`dev_logs/32_HBM_Demo_F12_四房间世界视图与全量UI同步方案.md`](32_HBM_Demo_F12_四房间世界视图与全量UI同步方案.md) — 全量 delta（**已完成**）
- [`dev_logs/24_HBM_Demo_Agent行为控制整合方案.md`](24_HBM_Demo_Agent行为控制整合方案.md) — ABCS（L2–L6）原设计
- [`dev_logs/29_HBM_Demo_F07_体验补强方案.md`](29_HBM_Demo_F07_体验补强方案.md) — F07-E（**大部分将退役**）

**关联代码**：`agent_world/hbm_demo/core/runner/`、`features/f07_agent_control/`、`features/f11_live_turn_sync/`、`features/f03_action_result/`

---

## 一、文档目的

本文是 **Agent 控制层 v2.0 的单一权威方案**，汇总产品/设计侧全部诉求，并给出：

1. **需求清单**（用户确认过的控制哲学）  
2. **目标架构**：后台世界 **常驻运转**（约 **1 tick / 秒**），玩家言语 **插入下一 tick 边界**  
3. **保留 vs 删除** 的控制项  
4. **分阶段实施** 与 **验收标准**  
5. **预期完成后的 Agent 控制整体形态**（运行时可观测行为）

---

## 二、需求汇总（Agent 控制相关 · 用户确认）

以下条目来自多轮讨论，作为 v2.0 的 **不可协商设计约束**：

| # | 需求 | v2.0 对策 |
|---|------|-----------|
| R1 | **只保留 L3「谁活跃」作为硬控制**；`frozen` = 本 Phase 不调 LLM（休眠，非从世界删除） | 保留 `pick_active` + `turn_control.yaml` |
| R2 | **关闭 L5 工具白名单硬拦截**（`do_nothing` 整拍作废） | 默认 `tool_guard.hard_block: false` |
| R3 | **取消 E1 / E2 / E3** 硬性限制（必须先 F2F、RDC 配额 do_nothing、Jensen 全文 notify） | 配置关闭 + 删批末/批首调用 |
| R4 | **取消 E1 scripted fallback**（模板替 Agent 写 F2F） | `scripted_f2f_fallback: false`，移除批末调用 |
| R5 | **取消固定 N tick inject 批**；**世界 loop 不因玩家 Turn 而停** | 常驻 loop **一直跑**；无「等批跑完」 |
| R6 | **后台世界一直跑**，约 **1 秒 1 tick**；玩家说话插入 **最近 tick 边界** | 新 **WorldLoopOrchestrator**（§四） |
| R7 | **所有 Agent 行为与世界变化必须反馈 UI**；不删 LLM 输出，只加强软引导 | F12 delta 已具备；Runner 不再 `do_nothing` 抹行为 |
| R8 | **地点移动 / Phase 切换** 走软引导 + **Flask 路由读 DB 信号**，不由 tool_guard 硬禁 | 知识库 + `story_advance` / RDC 链；MOVE 仅 Flask IPC |
| R9 | **知识库加入历史上下文**（我说过什么、谁对我说过、我做过什么） | L4 扩展 **thread recap**（§6.3） |
| R10 | **Stats 不参与 gate**；Phase 由 Agent 行为链驱动 | `routing.mode: agent_driven`（dev_logs/30 PR3） |
| R11 | **Prompt 透明**：每次行动 = soul + 状态 + 增量 observation + L4/L6 + 历史 recap | 文档化于 §六 |
| R12 | **inject_exclusive / passive_low_freq** 可保留为 **舞台调度**（非删行为） | 并入 L3，随常驻 loop 每 tick 生效 |
| R13 | **左栏功能按钮**：玩家可 **手动暂停 / 继续** 后台 world tick loop | StatusPanel **「暂停世界」** + IPC `PAUSE_LOOP` / `RESUME_LOOP`（§8.3） |
| R14 | **前端尽可能快捕捉每个 tick 变化**（含静默期 Agent 活动） | **F14 常驻 delta poll**（§十四）；当前 F11 **不满足** |
| R15 | **开发工具：行为/UI 记录点击反查 LLM Prompt**；Agent **地点变更历史** | **F15 Prompt Inspector**（§十六）；**无** 左栏独立「Prompt 日志」按钮 |

**明确不做（v1 / F07-E 遗留）**：

- ❌ `filter_tool_calls` → 整批 `do_nothing`  
- ❌ `apply_batch_f2f_fallback_at` 模板 F2F  
- ❌ `notify_jensen_player_summary`  
- ❌ Turn4 `V+E<15` Stats Bad End 硬 gate（改为 Agent 拒绝信号）  
- ❌ `completion` 依赖 fallback 产 F2F 才 `completed`  
- ❌ **Turn settle / idle 停 loop** — 世界 **不因**「静下来」而停止 tick

---

## 三、架构对比：v1 批模式 vs v2 常驻模式

### 3.1 v1（当前代码 · 待替换）

```text
玩家 POST player-turn
  → Flask 发 IPC INJECT（tick_count=12）
  → Runner for 循环跑满 12 tick
  → 批末 fallback / E3 notify
  → 批间时钟冻结
  → F03 polling 判 completed
```

**问题**：tick 多但落库少；硬守卫废掉 LLM；fallback 替 Agent 说话；与「活的世界」不符。

### 3.2 v2（目标 · 常驻世界）

```text
Runner 启动后
  → WorldLoopOrchestrator 后台 asyncio 任务
  → 每 ~1s: run_one_tick() 一次（全局时钟 t+=1）
  → 每 tick 前: drain PlayerInputQueue → DialogueInjection / player_memory
  → L3 pick_active 决定本 tick 谁调 LLM
  → 行为原样 dispatch 落 world.db
  → 写 loop_status.json（t, last_activity_t, pending_player）

玩家 POST player-turn
  → 仅 enqueue 玩家句 + turn_context 更新（不阻塞等 12 tick）
  → 返回 `{ accepted: true, stats_update, player_turn }`（**无** task_id / completed）
  → 下一 tick 边界 inject 生效；Agent 在随后 tick 自然回应

Flask GET action-result / F12 delta
  → since_tick 增量拉取；**世界 loop 不停**，UI 持续跟 tick 走
  → 玩家 POST 仅入队；**无**「等批跑完 / 等世界静下来再停 loop」（§5.4）
```

### 3.3 与 agent_world 引擎的关系

| 层级 | 职责 |
|------|------|
| **WorldStep 引擎** | 仍只提供 `run_one_tick()`；**不自停、不自启 loop** |
| **WorldLoopOrchestrator** | HBM 应用层：间隔、队列、L3 上下文；**loop 常驻不随 Turn 停** |
| **Flask/F11** | 玩家输入入队、剧情计数、路由、**连续 delta**（非批等待） |
| **F12 UI** | 订阅 delta，展示全 channel / 全 place |

---

## 四、WorldLoopOrchestrator（核心新组件）

### 4.1 职责

| 职责 | 说明 |
|------|------|
| **常驻 tick** | `while running: await run_one_tick(); await sleep_after_tick()` |
| **默认间隔** | `tick_interval_sec: 1.0`（**节拍 A**：上一 tick **完全结束**后再 sleep，见 §17.2） |
| **玩家输入队列** | FIFO；每 tick **开始前** drain → ScriptEngine inject |
| **turn_context** | 随 Phase / player_turn 更新；每 tick 传入 `HbmWorldStep.set_tick_context` |
| **L3** | 每 tick 调用 `pick_active_ids`（含 inject_exclusive、passive） |
| **活动检测** | 本 tick 若有新 `direct_message` / F2F / `update_state` / MOVE → 刷新 `last_activity_t` |
| **停止 loop** | **仅** `game_over`、**玩家左栏暂停**（`PAUSE_LOOP`）、Runner 进程退出；**不因** Turn、idle、API completed 而停 |

### 4.2 玩家言语如何「插入最近 tick」

**原则**：只能在 **tick 边界** 注入（引擎 observation 在 tick 开始时构建）。

```text
T=100  run_one_tick 开始
T=100  drain queue:
         - 玩家句 → DialogueInjection → Agent1 player_memory
         - turn_context.stats / phase 刷新
T=100  pick_active → Agent1 LLM（看到玩家句）
T=100  tick 结束，t=101

T=101  Jensen passive 可能看到 RDC（下 tick 送达语义不变）
```

**并发**：同一时刻只允许 **一个** WorldLoop 写 world；玩家连发多句 → 队列顺序处理，**每句占一个 tick 边界**（或合并为一条 inject，可配置）。

### 4.3 IPC 形态变化

| v1 | v2 |
|----|-----|
| `INJECT_SCRIPT_EVENT` + `tick_count=N` 同步跑 N tick | `INJECT_SCRIPT_EVENT` **仅 enqueue events**，不跑批 |
| 批间 frozen | 新增 `GET_LOOP_STATUS` / `env_status.loop_state` |
| — | **`PAUSE_LOOP` / `RESUME_LOOP`**（左栏按钮 + Flask API，§8.3） |
| `MOVE_AGENT` | **保留**（Flask 路由专用） |

`ipc_handlers.py` 中 **删除** `for _ in range(tick_loops)` 主路径，改为向 Orchestrator 投递。

### 4.4 配置文件（新建 `world_loop.yaml` 或并入 `turn_control.yaml`）

```yaml
world_loop:
  enabled: true
  tick_interval_sec: 1.0        # 目标 ~1 tick/s
  max_ticks_per_session: 10000  # 安全上限（整局）
  idle_pause_after_sec: 0         # 0=禁用；勿与用户「idle 不停 loop」冲突
  merge_player_burst: false     # true=同 tick 合并多句玩家话
  allow_manual_pause: true      # 左栏「暂停世界」是否可用
  pause_drains_queue: false     # false=暂停期间不 inject，队列保留

player_input:
  max_queue_depth: 32
  inject_on_tick_boundary: true

# 注意：无 turn_settle — 世界 loop 不因 Turn 而停（见 §5.4）
```

---

## 五、控制层分层（v2.0 最终形态）

### 5.1 硬控制（仅 L3 + 结构边界）

| 层 | 内容 | 说明 |
|----|------|------|
| **L3 活跃** | `primary_active`, `frozen`, `present_silent`, `inject_exclusive_ticks`, `passive_*` | **唯一**「谁本 tick 调 LLM」 |
| **结构边界** | Agent **不可** `request_move` / `send_to_group` 触发 Flask 路由 | 由 **dispatcher + Flask** 处理，非 L5 do_nothing |
| **WorldLoop 单写者** | 一次一个 tick | 防并发写 world.db |

**`frozen` 语义（再次确认）**：

- 该 Agent **本 Phase 永不进入 `pick_active_ids` 返回值**  
- **不会**调 `perform_action_by_llm`  
- 仍在 `agent_location`、F12 圆点仍在  
- ≠ 引擎删除 Agent

**`inject_exclusive_ticks`（常驻模式下）**：

- 指 **「自上次玩家 inject 起的前 N 个全局 tick」**，仅 inject 目标活跃  
- 实现：`turn_context.player_inject_tick` + `batch_tick_index = t - player_inject_tick`

**`passive_low_freq`**：

- 每 tick 在 primary 之后，对 CEO 等：有未读 RDC/F2F + 概率 + `passive_max_per_batch`（改为 **per player-turn 窗口** 计数）

### 5.2 软引导（主手段）

| 层 | 内容 |
|----|------|
| **L2** | temperature / max_tokens（`llm_params.py`） |
| **L4** | Phase bible、agent overlay、turn_hints、**thread recap**、session facts（**去掉 Stats 门槛文案**） |
| **L6** | inject 玩家 verbatim、角色 checklist、行为顺序 **建议**（非强制） |
| **Soul** | `hbm_scenario.yaml` → PerceptionBuilder system 段 |
| **Observation** | 引擎增量：新到私信、F2F feed、同室、移动 diff |
| **HbmAgent 尾段** | 短行动建议；**不得**再写「违规将被拒绝」类硬威胁（L5 已关） |

### 5.3 删除或默认关闭（硬控退役）

| 模块 | v2 处理 |
|------|---------|
| `tool_guard` E1/E2 → do_nothing | **默认关闭**；可选 `rewrite_mode`（speak_to_local 改写）仅日志，**第一版不做** |
| `tool_matrix` → do_nothing | **关闭**；矩阵仅作文档/监控 |
| `f2f_fallback` | **不调用** |
| `notify_jensen_player_summary` | **删除调用** |
| `experience_hardening.inject_exclusive` 作为 **禁令** | 保留为 **L3 调度**，非 guard |
| 固定 `tick_count=12` | **删除** |
| `check_action_complete` 批等待 | **废弃**；改为 **连续 delta**（§5.4） |

### 5.4 世界不停 vs 玩家 Turn（重要 · 易混）

此前文档中的 **「Turn settle / 世界静下来再停」** 表述 **有误**，容易理解成「世界 loop 要停」。你的需求是：

> **后台世界一直跑；没有等批跑完；loop 不因玩家输入而启停。**

因此 v2.0 **严格区分两件事**：

| 概念 | 是否停止 world loop | 说明 |
|------|---------------------|------|
| **World loop** | **默认不停**（除 **左栏 pause** / `game_over` / 进程退出） | 约 1s 一次 `run_one_tick()`（节拍见 §13.3 A） |
| **玩家 POST player-turn** | **不停 loop** | 仅向 `PlayerInputQueue` **入队**；下一 tick 边界 inject |
| **player_turn 计数** | **不停 loop** | POST 时 `player_turn += 1`（或入队时 +1）；用于 L4 hints / 路由窗口 |
| **F03 action-result** | **不停 loop** | 改为 **`since_tick` 连续增量**；无 `processing→completed` 批等待 |
| **F05 routing** | **不停 loop** | 后台 **每 tick 或每 N tick** 扫 world.db；满足信号则 IPC MOVE |

```text
❌ 错误理解（v1 / 旧稿）:
  玩家说话 → 开一批 tick → 跑满或 idle settle → 停 loop → 等下一句

✅ 正确理解（v2 · 你的需求）:
  Runner 启动 → loop 永远转（1 tick/s）
  玩家随时说话 → 入队 → 下一 tick 边界生效
  Agent 在后续 tick 自然回应；世界不因「回应完」而停
  UI 用 since_tick 一直拉 delta；routing 在 loop 旁路读 DB
```

**废弃的 API 语义**（实施时删除或降级）：

- `inject_status: RUNNING → DONE` 批生命周期  
- `check_action_complete` 等 idle / max_ticks 才 `completed`  
- `ipc_end_tick` 作为 Turn 边界  

**保留的产品语义**：

- **25 轮 player_turn**：仅 **剧情计数** 与 turn_hints，**不**绑定 loop 启停  
- **Phase / MOVE**：routing 读 DB 信号，在 **loop 仍在跑** 时触发

---

## 六、Prompt 组成（每次 Agent 行动前）

一次 LLM 调用 = **system + user** 两条 message。

### 6.1 System（PerceptionBuilder）

来自 `hbm_scenario.yaml`，五段：

```text
# Soul
# Long-term Goal
# Current State
# Short-term Goal
# Place Behavior Rule   ← 当前 place.attrs
```

### 6.2 User（HbmAgent._observation_to_text）

按顺序拼接：

| 块 | 来源 | 谁看得到 |
|----|------|----------|
| **玩家/注入记忆** | `player_memory`（L6 + L4 全文） | inject 目标；drain 后本 tick 可见 |
| **剧本 notification** | `build_notification_snippet` | 非 inject 的 primary |
| **Thread recap（新）** | L4 从 world.db 聚合 | 所有 active Agent |
| **引擎 observation** | 新到 RDC/F2F、同室、feeds、移动 diff | 所有 active Agent |
| **行动建议尾段** | `_hbm_short_action_rules` | 软引导，无硬拦截威胁 |

### 6.3 L4 Thread Recap（R9 新增）

每 tick 前为 active Agent 生成 **只读摘要块**（非 if-else 剧情）：

```text
【近期对话摘要】
- 前台→你(F2F@reception, t=98): 「…」
- Jensen→VP(RDC, t=99): 「…」
- 你→Jensen(RDC, t=97): 「…」
【你最近 OS】update_state @ t=96: 「…」
```

数据源：`direct_message`、`fetch_f2f_history_at`、可选 `agent_state_log`（F12 已落库）。

**不做**：把全文 history 塞进 prompt（控 token）；摘要窗口 `recap_window_ticks: 20`。

---

## 七、路由与世界后果（R8 / R10）

与 dev_logs/30 PR3 一致，**Stats 仅展示**：

| 节点 | agent_driven 信号（读 world.db） |
|------|----------------------------------|
| A → Phase2 | RDC 链 1→2 + 2→3 + 2→1 approve + 可选 `story_advance(approve_visitor)` |
| B → Phase3 | Phase2 窗口 VP→Jensen 正面 RDC + approve 类语义 |
| C → Phase4 | Phase3 结束信号 / CEO 被驱逐 / negotiation 恢复 |
| Bad End | 前台 F2F 明确拒绝 / `story_advance(reject_visitor)` |

**MOVE / PlaceMutation**：仅 **Flask `routing.apply_routing`** 发 IPC MOVE；Agent `request_move` 即使被 LLM 调用也不执行路由（dispatcher 层 **静默忽略 + 软知识库说明**），**不 do_nothing 整拍**。

---

## 八、Flask / UI 配合（F11 + F12）

### 8.1 API 行为变化

| API | v2 |
|-----|-----|
| `POST /player-turn` | 入队 + 立即返回；`player_turn += 1`；**不**阻塞 loop |
| `GET /action-result` | **`since_tick` 连续 delta**；无 processing/settle 等待 |
| F12 delta | UI 按 tick 增量拉取；loop **一直跑** |

### 8.2 玩家体验

- 说话后 **~1–3 秒** 内可见前台 F2F（取决于 inject_exclusive + LLM 延迟）  
- 不说话时 **手机面板 / WorldStage** 仍可能动（Jensen↔VP RDC、CEO passive）  
- 所有 channel **进 F12**，不再「Runner 删了 Flask 看不到」  
- 需要 **冻结观察** 或 **省 LLM 成本** 时，点左栏 **「暂停世界」**，tick 不再递增

### 8.3 左栏「暂停世界 / 继续世界」控制（R13 · F13）

#### 8.3.1 产品定位

常驻 loop（§四）默认 **一直跑**；但 Demo 需要 **玩家可主动冻结世界** 的能力，用于：

- 暂停后台 Agent 继续说话 / RDC，便于 **读 UI、截图、讲解**  
- **控制 LLM 成本**（调试、反复试同一场景）  
- 与「Turn 批等待」**无关**：暂停 **只停 tick loop**，不表示 Turn 完成

**位置**：左栏 `StatusPanel` 底部，与 **「重开」** 并列（`status-panel__footer`：`暂停世界` + `重开`）。

#### 8.3.2 UI 规格（F12 左栏 StatusPanel）

| 元素 | 规格 |
|------|------|
| **按钮文案（运行中）** | `暂停世界` |
| **按钮文案（已暂停）** | `继续世界` |
| **样式** | 与 `status-panel__reset-btn` 同级；暂停态可用 `--paused` 变体（如描边/琥珀色） |
| **World tick 行** | `World tick: 142` — **暂停时数字冻结**；旁可加 `(已暂停)` 小标签 |
| **禁用** | `game_over`、Runner 未就绪、`resetDisabled` 同类逻辑下禁用 |
| **重开** | 重开前若 paused，先 `RESUME` 或直接 `RESET_WORLD` 一并清 loop 状态 |

**布局示意**（dev_logs/32 §6.1 左栏不变，仅 footer 扩展）：

```text
┌─ Status ─────────────────┐
│ 核心数值 / Phase / Turn  │
│ World tick: 142 (已暂停) │
├──────────────────────────┤
│ [ 暂停世界 ]  [ 重开 ]    │
└──────────────────────────┘
```

**前端状态**（`gameStore` 或局部 state）：

```typescript
worldLoopState: 'running' | 'paused' | 'unknown'
worldLoopPausedAtTick?: number
```

- 启动时 `GET /world-loop/status` 或读 delta/env 同步  
- 点击 → `POST /world-loop/pause` 或 `POST /world-loop/resume` → 更新本地 state  
- `useGameLoop` polling：`worldLoopState === 'paused'` 时 **仍可拉 delta**（只读），但 `worldTick` 不再变

#### 8.3.3 后端 API（Flask · 新建 `features/f13_world_loop_control/`）

| 方法 | 路径 | 行为 |
|------|------|------|
| `GET` | `/simulations/{sim_id}/world-loop/status` | 返回 `{ loop_state, current_tick, … }` |
| `POST` | `/simulations/{sim_id}/world-loop/pause` | IPC `PAUSE_LOOP` |
| `POST` | `/simulations/{sim_id}/world-loop/resume` | IPC `RESUME_LOOP` |

也可合并为 `POST /api/world-loop/toggle`，首版 **两个 explicit 端点** 更清晰。

**错误**：

- Runner 未就绪 → `503 RunnerNotReady`  
- 已 paused 再 pause / 已 running 再 resume → `409` 或幂等 200  

#### 8.3.4 Runner IPC 与 Orchestrator 行为

**IPC 命令**（`agent_world/ipc/commands.py` 扩展）：

| 命令 | payload | 返回 |
|------|---------|------|
| `PAUSE_LOOP` | `{}` | `{ loop_state: 'paused', paused_at_tick, world_t }` |
| `RESUME_LOOP` | `{}` | `{ loop_state: 'running', world_t }` |
| `GET_LOOP_STATUS` | `{}` | `{ loop_state, world_t, tick_interval_sec, queue_depth? }` |

**`WorldLoopOrchestrator` 暂停语义**：

```text
running:
  sleep(tick_interval_sec)
  drain queue → run_one_tick() → t+=1

paused:
  不调用 run_one_tick()
  不 sleep 推进 tick（asyncio Event wait，直到 resume）
  world.t 冻结在 paused_at_tick
```

| 维度 | 暂停时行为 |
|------|------------|
| **全局时钟 `t`** | **冻结** |
| **PlayerInputQueue** | **仍可入队**（玩家可打字）；**不 drain** 直到 resume（`pause_drains_queue: false`） |
| **L3 / LLM** | **不执行**（无 tick 即无 pick_active） |
| **F05 routing 旁路** | **暂停扫库**（可选：resume 后立刻扫一次） |
| **F12 delta polling** | 允许；返回自 `since_tick` 起的 **已有** 数据，无新 tick 则无新事件 |
| **game_over** | 强制 `paused` 且按钮禁用 |

**恢复**：从 **同一 `t`** 继续；队列中积压的玩家句在 **下一 tick 边界** 按 FIFO drain。

#### 8.3.5 env_status.json 扩展

```json
{
  "status": "running",
  "current_tick": 142,
  "loop_state": "paused",
  "paused_at_tick": 142,
  "paused_at_iso": "2026-05-23T12:00:00Z",
  "tick_interval_sec": 1.0
}
```

Flask / 前端可轮询此文件或通过 API 代理，与 `worldTick` 展示一致。

#### 8.3.6 与「世界常驻跑」的关系（澄清）

| 场景 | loop |
|------|------|
| 默认进游戏 | **running**（~1 tick/s） |
| 玩家点「暂停世界」 | **paused**（玩家主动） |
| 玩家点「继续世界」 | **running** |
| 玩家 POST 台词 | **不改变** loop 状态；暂停时入队等候 |
| Turn / 批 / idle | **永不**自动 pause |

左栏暂停是 **唯一的「正常运行中可停 tick」入口**（另：`game_over`、进程退出）。

#### 8.3.7 实施清单（并入 Phase 1b / Phase 2）

**Runner（Phase 1b）**

- [ ] `WorldLoopOrchestrator.pause()` / `resume()` + `asyncio.Event`  
- [ ] IPC handlers：`PAUSE_LOOP` / `RESUME_LOOP` / `GET_LOOP_STATUS`  
- [ ] `env_status` 写入 `loop_state`  

**Flask（Phase 1b）**

- [ ] `features/f13_world_loop_control/handler.py`  
- [ ] 注册路由于 `game_service.py`  

**前端（Phase 2）**

- [ ] `StatusPanel.tsx`：`onPauseWorld` / `onResumeWorld`、`worldLoopState`  
- [ ] `App.tsx` / `useGameLoop`：API 调用 + store  
- [ ] `global.css`：`.status-panel__pause-btn`、`.status-panel__tick--paused`  

**验收**

- [ ] 点「暂停世界」→ 5 秒内 `worldTick` 不变；DB `current_tick` 不变  
- [ ] 暂停期间 Jensen 无新 RDC 落库  
- [ ] 点「继续世界」→ tick 恢复每秒 +1；队列中玩家句在下一边界 inject  
- [ ] 与「重开」不冲突  

---

## 九、分阶段实施

### Phase 0 — 硬控退役（P0，可独立 PR）✅ 2026-05-23

- [x] `turn_control.yaml`: `experience_hardening.enabled: false`, `scripted_f2f_fallback: false`, `tool_guard.hard_block: false`
- [x] `inject_exclusive_ticks` 迁入 `phases.Phase 1`（不再绑 hardening）
- [x] `tool_guard`: `hard_block: false` — 丢弃非法 tool，不再 mass `do_nothing`
- [x] 移除 `ipc_handlers` 批末 fallback + E3 `notify_jensen_player_summary` 调用
- [x] `HbmActionDispatcher` — agent `request_move` 静默 no-op
- [x] `completion.py` — 连续 delta 读模型（废弃 v2 下 ipc_end-only completed）
- [x] 验收：`test_m0_acceptance` + F12 回归全通过

### Phase 1 — WorldLoopOrchestrator（P0）

- [ ] `core/runner/world_loop.py` — asyncio loop + 1s interval  
- [ ] `PlayerInputQueue` — thread-safe，IPC/Flask 写入  
- [ ] 改 `run_hbm.py` — 启动 loop task + IPC forever  
- [ ] 改 `ipc_handlers` — inject 仅 enqueue  
- [ ] 改 `f02` / `f11` — 不再 `send_inject_batch(tick_count=12)`  
- [ ] `env_status.json` 增加 `loop_running`, `last_activity_t`  
- [ ] 验收：Runner 启动后无玩家 input 时 t 仍每秒 +1；玩家 POST 后下 tick 可见 inject  

### Phase 1b — 左栏暂停世界（P0 · R13）

- [ ] §8.3 Runner IPC + Orchestrator pause/resume  
- [ ] §8.3 Flask `/api/world-loop/*`  
- [ ] §8.3 StatusPanel 双按钮 + tick 冻结展示  
- [ ] 验收：见 §8.3.7  

### Phase 2 — 连续 delta API + F14 常驻 poll（P1）

- [ ] `get_action_result`：仅 `since_tick` 增量，去掉 `processing/completed` 批语义  
- [ ] **F14** `GET /world-delta?since_tick=`（session 级，无 task_id）— 见 §十四  
- [ ] 前端 `useWorldDeltaPoll`：游戏进行中 **常驻** poll（≤500ms），与 `sendTurn` 解耦  
- [ ] `useGameLoop`：去掉等 `completed` 的 for-loop；玩家 POST 仅入队  
- [ ] `F05 routing`：loop 旁路定时扫 DB（每 tick 或每 5 tick）  
- [ ] 验收：玩家 **不说话** 时 Jensen RDC 仍能在 UI 出现；tick 变化延迟 **≤ poll 间隔 + 1 网络 RTT**

### Phase 3 — L4 recap + prompt 清理 + **F15 Prompt Inspector**（P1）

- [ ] `knowledge.build_thread_recap(agent_id, t, window)`  
- [ ] 去掉 L4 中 Stats 门槛文案  
- [ ] 软化 `_hbm_short_action_rules` 硬威胁语句  
- [ ] **F15** §十六：`agent_llm_trace` + link + API + UI 点击反查 + 地点记录线程（**无**全局 Prompt 浏览器）
- [ ] 验收：prompt 审计脚本；Jensen 无 E3 全文；§16.9 全通过  

### Phase 4 — agent_driven routing（P2）

- [ ] `routing.yaml` `mode: agent_driven`  
- [ ] 节点 A/B/C 读 DB 信号  
- [ ] Turn4 Stats bad end 改为信号驱动  
- [ ] 验收：`test_m0_acceptance` routing 段 + 手玩 Phase1→2  

### Phase 5 — 可选增强（P3）

- [ ] `story_advance` 信号 tool（落库，路由读）  
- [ ] loop `idle_pause_after_sec` 省电  
- [ ] WebSocket 推 delta（替代高频 polling）  

---

## 十、预期完成后的 Agent 控制整体形态

完成 v2.0 后，从 **开发者 / 玩家 / 审计** 三视角描述如下。

### 10.1 运行时拓扑

```text
┌──────────────────────────────────────────────────────────────┐
│ Flask 应用层                                                  │
│  player-turn → InputQueue                                     │
│  action-result / F12 delta ← ReadOnlyWorldDB (since_tick)     │
│  routing (agent_driven) → IPC MOVE only                       │
└───────────────────────────┬──────────────────────────────────┘
                            │ IPC enqueue / MOVE
┌───────────────────────────▼──────────────────────────────────┐
│ HBM Runner                                                    │
│  WorldLoopOrchestrator  (~1 tick/s)                           │
│    tick 前: drain queue → inject                              │
│    tick 中: L3 pick_active → HbmAgent LLM → dispatch 落库     │
│    tick 后: 更新 last_activity / loop_status                  │
│  【无】L5 do_nothing / fallback / E3                          │
└───────────────────────────┬──────────────────────────────────┘
                            │ run_one_tick()
┌───────────────────────────▼──────────────────────────────────┐
│ WorldStep 引擎（agent_world 核心）                             │
│  11 步 pipeline · t+=1 · 不自停                               │
└──────────────────────────────────────────────────────────────┘
```

### 10.2 一次玩家说话的时序（预期）

| 时间 | 事件 |
|------|------|
| T+0.0s | 玩家提交 Turn5 台词 |
| T+0.1s | Flask 202 入队；`player_turn += 1`；UI 开始 **since_tick 增量 poll**（无 completed 卡点） |
| T+0.0–1.0s | 当前 tick 可能正在进行；玩家句等 **下一 tick 边界** |
| T+1.0s | drain → Agent1 `player_memory` 含 L4+L6+玩家句 |
| T+1.0–4.0s | tick 内 LLM；可能 F2F + RDC 落库 |
| T+2.0s+ | Jensen/VP passive tick；Observer 出现 RDC；**loop 不停** |
| T+任意 | routing 扫 DB 满足链 → IPC MOVE；**loop 仍跑** |
| 全程 | UI `since_tick` 持续拉 delta；**无** completed 卡点 |

### 10.3 控制项一览（完成后）

| 控制 | 硬/软 | 完成后行为 |
|------|-------|------------|
| 谁调 LLM | **硬 L3** | frozen 永不 tick；inject_exclusive 限前 N tick 仅前台 |
| 说什么 | **软** | 100% LLM；知识库 + recap 引导 |
| 工具选择 | **软** | 不 do_nothing；MOVE/GRP 无效但不禁言 |
| tick 节奏 | **编排** | 默认 ~1s/tick **常驻**；左栏可 **pause** |
| player_turn | **计数** | POST 时 +1；不绑定 loop 启停 |
| Phase 切换 | **后果** | routing 旁路读 DB；**paused 时 routing 也暂停** |
| UI 可见性 | **F12 全量** | 所有落库行为可 delta |
| **世界暂停** | **玩家控制** | 左栏「暂停世界 / 继续世界」→ IPC（§8.3） |
| **Prompt 调试** | **开发工具 F15** | **点击** 消息/OS/地点行 → Prompt（§十六）；无左栏日志按钮 |
| **地点历史** | **Agent 手机** | 「地点记录」线程 + delta `locationLog`（§16.7.2） |

### 10.4 与 v1 的可观测差异

| 观测 | v1 | v2 完成后 |
|------|-----|-----------|
| `current_tick` | 仅 Turn 时跳 12 | **持续每秒 +1** |
| 中屏 F2F | 常是 fallback 模板 | **LLM speak_to_local** |
| Turn 等待 | 固定批长 + polling completed | **无等待**；delta 跟 tick 走 |
| 静默期 UI | 不动 | **Jensen/VP/CEO 仍可能动** |
| world.db | 7 条/2 Turn | **同 tick 密度更高、链更完整** |

### 10.5 风险与缓解

| 风险 | 缓解 |
|------|------|
| LLM 成本（常驻 tick） | L3 frozen + passive 概率；`idle_pause`；primary 外少 tick |
| 玩家句延迟 1 tick | 可接受；可调 `tick_interval_sec` |
| 路由误判 | 可选 `story_advance`；保留 `legacy_stats` flag |
| LLM 过慢 | tick 间隔与 LLM 并行；可配置单 tick 内 timeout skip |

---

## 十一、FAQ

**Q：frozen Agent 是「死亡」吗？**  
A：否。只是本 Phase **不调 LLM**；位置与 UI 仍在。

**Q：引擎会自动停吗？**  
A：`WorldStep` 不会。`WorldLoopOrchestrator` **默认常驻跑**；可因 **左栏「暂停世界」**、`game_over`、进程退出而停 tick。**没有**「Turn 完成 → 停 loop」。

**Q：左栏「暂停世界」和 Turn 完成是一回事吗？**  
A：**不是**。暂停只冻结 **tick loop** 与 **时钟 t**；玩家仍可看 UI、可入队台词；点「继续世界」后从同一 tick 接着跑。Turn 计数与 pause **无关**。

**Q：那 player-turn 还算「Turn」吗？**  
A：算 **剧情轮次计数**（1–25），用于 hints 与路由窗口；**不是**「开一批 tick 再停」的批边界。

**Q：1 秒 1 tick 是否太慢？**  
A：可配置。1s 是 Demo 默认，平衡成本与「活的世界感」；LLM 延迟通常 >> 1s，瓶颈在模型而非 sleep。

**Q：还要 dev_logs/30 吗？**  
A：30 中 PR1/PR3/PR4 仍有效；**PR2 quota 锁、固定 12 tick** 被本文 §四、§五 取代。F12（PR4）已完成。

**Q：L5 完全删除吗？**  
A：代码保留 **监控/文档**；**默认不拦截**。结构动作（MOVE/GRP）在 dispatcher 层忽略，不用 do_nothing。

---

## 十二、代码索引（v2 新增/变更）

| Topic | Path |
|-------|------|
| World loop（新） | `core/runner/world_loop.py`（待建） |
| Player queue（新） | `core/runner/player_input_queue.py`（待建） |
| Runner 入口 | `core/runner/run_hbm.py` |
| IPC | `core/runner/ipc_handlers.py` |
| L3 | `features/f07_agent_control/pick_active.py` |
| 软引导 L4/L6 | `features/f07_agent_control/knowledge.py` |
| 连续 delta | `features/f03_action_result/handler.py`（废弃 completion 批语义） |
| 玩家 Turn | `features/f02_player_turn/handler.py` |
| 后台 pipeline | `features/f11_live_turn_sync/async_inject.py` |
| 路由 | `features/f05_story_routing/routing.py` |
| F12 delta | `features/f12_world_sync/delta.py` |
| 配置 | `features/f07_agent_control/turn_control.yaml`, `world_loop.yaml`（待建） |
| 世界 pause UI/API（新） | `features/f13_world_loop_control/`, `web/.../StatusPanel.tsx` |
| **F14 常驻 delta poll（新）** | `features/f14_world_delta/`, `web/.../useWorldDeltaPoll.ts` |
| **F15 Prompt Inspector（新）** | `features/f15_prompt_trace/`, `web/.../PromptTraceModal.tsx`, `LocationHistoryTimeline.tsx`（**无** PromptBrowser 页） |
| F11（现状 · 将演进） | `features/f11_live_turn_sync/delta.py`（薄封装 F12；**task 绑批**） |

---

**文档版本**：v2.5 · 2026-05-23（§17.2 ①② 定稿 · 节拍 A + SessionMirror 规格）  
**分支**：`feature/agent-control`  
**下一步**：Phase 0 → Phase 1 loop → Phase 1b pause → Phase 2 F14 → Phase 3 F15 + recap

---

## 十三、方案审查（2026-05-23）

### 13.1 总体结论

| 维度 | 结论 |
|------|------|
| **能否达到预期效果** | **能**，方向与用户诉求（常驻 loop、软引导、L3-only 硬控、F12 全量反馈、左栏 pause）一致 |
| **当前代码** | **≈0% 落地**；仍 100% v1 批模式 + F07-E 硬守卫（见 §13.2） |
| **方案完整度** | **约 95%**（§17.2 ①② 已定稿；③–⑥ 按文档默认执行） |

### 13.2 代码现状 vs 方案（快照）

| 方案项 | 代码状态 |
|--------|----------|
| WorldLoopOrchestrator / PlayerInputQueue | ❌ 不存在 |
| INJECT 仅 enqueue | ❌ `ipc_handlers.py` 仍 `for _ in range(tick_loops)` |
| L5/E1/E2/fallback/E3 关闭 | ❌ `turn_control.yaml` 全开；`tool_guard` 仍 mass `do_nothing` |
| 连续 delta / 无批 completed | ⚠️ F12 delta 有；`useGameLoop.ts` 仍 poll 至 `completed` |
| L3 pick_active | ✅ 已有；`batch_tick_index` 仍绑 **inject 批** 生命周期 |
| F12 UI 全量 | ✅ 已完成 |
| pause/resume / f13 API | ❌ 无 IPC、无路由、StatusPanel 仅「重开」 |
| L4 thread recap | ❌ 未实现 |
| agent_driven routing | ❌ `node_a_applies` 仍 Turn4 + Stats |

### 13.3 方案内待补充项（实施前必须定稿）

#### A. Tick 调度 vs LLM 延迟（**高优先级 · 当前未写**）

§四 写「~1s 1 tick」，但未定义 **LLM 慢于 1s** 时的行为。Phase1 `primary_active: [1,2,3]` 可能 **同 tick 并行 3 次 LLM**，单次 3–10s 很常见。

**建议写入方案（二选一，默认 A）**：

| 模式 | 行为 |
|------|------|
| **A · 串行节拍（推荐）** | `tick_interval_sec` = **上一 tick 完全结束后** 再 sleep；实际节拍 ≥ max(1s, LLM 耗时) |
| B · 固定墙钟 | 每 1s 触发下一 tick，可重叠（**不推荐**，并发写 world.db） |

#### B. `turn_context` 常驻同步（**高优先级**）

L3 依赖 `HbmWorldStep.set_tick_context`。v1 仅在 inject 批内设置；v2 loop **每 tick 都需要** phase / player_turn / stats / inject_agent_ids。

**需补充**：

- Runner 持 **session 快照**（Flask POST `/player-turn` 或 `/session` 时 IPC 更新 `UPDATE_TURN_CONTEXT`）  
- **无 tick_context 时禁止 fallback 到「全员 tick」**（`world_step._pick_active` 当前会 `super()` 全员活跃 → 成本爆炸）

#### C. 玩家 POST 语义（**中优先级**）

文档写 POST 入队 + `player_turn += 1`，但未写：

| 问题 | 建议 |
|------|------|
| **F04 `score_player_turn`** | 仍在 **Flask POST 线程** 立即算 delta 并写 session，再 IPC 入队 |
| **连发多句** | 队列 FIFO；每句独立 inject event；`inject_exclusive` 以 **该句 inject 的 t** 重置 |
| **`inject_agent_ids`** | 仍走 `routing.build_inject_payload`（同 Phase 决定前台/ Jensen 等） |
| **`clear_player_memory`** | 每次 drain **前** 对 inject 目标清 `player_memory`（沿用 v1 `turn_context` 逻辑） |

#### D. L3 计数器在常驻模式下的重置（**中优先级**）

| 字段 | v1 | v2 应对 |
|------|-----|---------|
| `batch_tick_index` | inject 批内递增 | 改为 `t - player_inject_tick`（§5.1 已述，**需改 `world_step.py`**） |
| `passive_ticks_so_far` / `passive_max_per_batch` | per inject 批 | 改为 **自上次 player inject 起** 计数，inject 时清零 |
| `BatchGuardState` | E1/E2/fallback 用 | 硬控退役后 **可删除或仅监控** |

#### E. Routing 旁路落点（**中优先级**）

§5.4 写「每 tick 或每 N tick 扫 DB」，但未指定 **谁扫**。

**建议**：

```text
WorldLoopOrchestrator 每 tick 结束后（或每 5 tick）:
  → IPC 回调 Flask 太重；应在 Runner 内嵌 RoutingScanner（只读 DB + 发 MOVE IPC）
  或 Flask 后台线程读 env_status.current_tick 变化时 apply_routing
```

首版：**Runner tick 末** 调用轻量 `routing.scan_if_needed(session_snapshot, t)`，MOVE 仍经现有 IPC。

#### F. `request_move` / GRP 静默忽略（**中优先级**）

§七 写 dispatcher 静默忽略，**当前代码未实现**；L5 禁 tool 时整拍 `do_nothing`。Phase 0 关 L5 后 Agent 可能发出 MOVE tool — **需在 HBM dispatcher 或 ActionDispatcher 层显式 no-op + 日志**，并写入 Phase 0 清单。

#### G. 文档内部不一致（**低优先级 · 应修**）

| 位置 | 问题 |
|------|------|
| §5.4 表「World loop 永不」 | 漏写 **左栏 pause**（§8.3 已写，此处应统一） |
| §10.2 | 仍写 `UI task=processing`，与 §5.4 废弃批语义 **矛盾** |
| §4.4 `idle_pause_after_sec` | 与用户「不因 idle 停 loop」冲突 → **默认 0 / 禁用**，仅调试可选 |
| §8.3.6 vs §8.3.6「左栏唯一正常暂停入口」 | `idle_pause` 若启用会冲突 → 配置注释标明 **默认 off** |

#### H. RESET / game_over 与 loop（**低优先级**）

**需补充**：

- `RESET_WORLD`：清空 PlayerInputQueue、`loop_state=running`、session tick=0、重启 loop  
- `game_over`：`PAUSE_LOOP` + 禁用左栏按钮（§8.3 已述）；Flask 返回 `game_over` 时前端停止 poll 即可

#### I. 测试与 dev_logs/30 关系（**低优先级**）

- `test_m0_acceptance.py` 大量断言 v1 E1/E2/fallback → Phase 0 需 **新增 v2 用例 / 改断言**  
- dev_logs/30 PR1（guard 改写）被本文 **「关 hard_block」** 取代；PR3/PR4 仍有效 → 在 30 文首加 **「批模式已被 31 v2 取代」** 注记

### 13.4 能否达成各 R 需求（实施后）

| 需求 | 可达性 | 依赖 |
|------|--------|------|
| R1–R4 去硬控 | ✅ | Phase 0 |
| R5–R6 常驻 loop | ✅ | Phase 1 + §13.3 A/B |
| R7 F12 反馈 | ✅ | 已完成 + Phase 0 不删行为 |
| R8 软引导 MOVE | ⚠️ | Phase 0 + §13.3 F dispatcher |
| R9 thread recap | ✅ | Phase 3 |
| R10 agent_driven | ⚠️ | Phase 4；链式 NL 误判风险仍在 |
| R11 prompt 透明 | ✅ | Phase 3 + 现有 PerceptionBuilder |
| R12 L3 调度 | ✅ | Phase 1 + §13.3 D |
| R13 左栏 pause | ✅ | Phase 1b |
| R14 每 tick UI | ⚠️→✅ | Phase 2 F14（当前 F11 **否**） |
| R15 Prompt 可追溯 | ✅ | Phase 3 F15（§十六） |

### 13.5 建议实施顺序（审查后确认）

```text
Phase 0（硬控退役 + dispatcher MOVE no-op）  ← 可先验证 LLM 真实落库
  ↓
Phase 1（Orchestrator + Queue + turn_context 常驻 + §13.3 A/B/D/E）
  ↓
Phase 1b（pause/resume UI + IPC）
  ↓
Phase 2（前端常驻 poll + 废弃 completed）
  ↓
Phase 3–4（recap + agent_driven routing）
```

**不建议** 跳过 Phase 0 直接做 loop：硬 guard 仍会 mass `do_nothing`，常驻 loop 只会 **更频繁空转**。

---

## 十四、F11 增量同步 vs 常驻 tick（F14 · 待实施）

### 14.1 结论：**当前 F11 无法尽可能快捕捉每个 tick**

| 能力 | 当前 F11 | v2 需要 |
|------|----------|---------|
| **何时 poll** | 仅 **玩家 POST 后** `sendTurn` 内 | **整局游戏进行中** 常驻 poll |
| **poll 间隔** | `POLL_INTERVAL_MS = 800ms`（`web/.../gameLoop.ts`） | **≤500ms** 或 `tick_interval_sec/2` |
| **绑定 task** | `GET /action-result?task_id=&since_tick=` + `PendingTask.start_tick` | **session 级** `since_tick`，无 task 边界 |
| **静默期世界** | **不 poll**；Jensen/VP RDC **不会**自动上 UI | loop 跑着就必须持续 merge delta |
| **tick 数字** | `useEnvStatus` 每 **1000ms** 读 `current_tick` | 已有；但 **不含** 消息/移动/OS |
| **停止 poll** | `sendTurn` 结束或 `completed` | `game_over` / 未初始化；**pause 时仍可读** delta |

**数据流（现状）**：

```text
玩家 POST → F11 async_inject 跑批 → env current_tick 变化
  → useGameLoop 仅在 loading 时 poll action-result
  → build_turn_delta (F11) → build_world_delta (F12)
  → APPLY_WORLD_DELTA

玩家不说话 / Turn 之间 → 无 poll → UI 冻结（仅 env tick 数字可能变）
```

这与 §四「后台世界一直跑」**不兼容**：静默期 Agent 行为 **前端看不到**。

### 14.2 延迟估算（现状 vs 目标）

| 场景 | 现状最坏延迟 | F14 目标 |
|------|-------------|----------|
| 玩家 Turn 内某 tick 落库 | **0–800ms**（poll 间隔）+ RTT | **0–500ms** + RTT |
| 玩家 Turn 内 + inject 批未开始 | 等 IPC 批跑完才有 tick | 每 tick 即时（loop 模式） |
| **静默期** passive RDC | **∞（不更新）** | **≤500ms** |
| pause 期间 | N/A | tick 不变；poll 可降频至 2s |

### 14.3 F14 设计方案（写入 Phase 2）

#### 后端

| 项 | 规格 |
|----|------|
| **新端点** | `GET /simulations/{sim_id}/world-delta?since_tick=N` |
| **实现** | `features/f14_world_delta/` 或扩展 `f12_world_sync/delta.py` |
| **payload** | 与 F12 `build_world_delta` 相同字段，但 **不依赖 PendingTask**；`since_tick` + `env.current_tick` 为窗口 |
| **session 绑定** | 读 Flask session 的 `place_id` / phase；`player_place_id` 来自 session |
| **与 F11 关系** | F11 `build_turn_delta` **deprecated**；F11 目录保留 task_state 直至批语义完全移除 |

#### 前端

| 项 | 规格 |
|----|------|
| **新 hook** | `useWorldDeltaPoll({ enabled, sinceTick, onDelta })` |
| **启用条件** | `sessionInitialized && view===playing && !game_over` |
| **间隔** | `DELTA_POLL_MS = 500`（可配置；**≤ tick_interval_sec**） |
| **与 sendTurn** | **解耦**：POST 后不再 for-loop poll；仅 `sinceTick` 由 store 维护 |
| **与 useEnvStatus** | 可合并：delta 响应含 `through_tick`，顺带更新 StatusPanel tick |
| **pause** | `loop_state===paused` 时仍 poll（读已有 DB）；可选降频 |

```text
App mount (playing)
  → useWorldDeltaPoll 每 500ms
  → GET /world-delta?since_tick=store.worldTick
  → APPLY_WORLD_DELTA
  → store.worldTick = delta.through_tick

玩家 POST
  → 仅 postPlayerTurn + 本地气泡
  → delta poll 自然捕捉后续 tick（无需 task_id）
```

#### 验收

- [ ] loop running、玩家 **0 输入** 30s：UI 可见 Jensen↔VP RDC（若 L3 passive 触发）  
- [ ] 单次 F2F 落库后 **≤1s** 内 WorldStage 气泡出现  
- [ ] pause 后 tick 数字不变；resume 后 delta 继续增量  
- [ ] 与 F12 `APPLY_WORLD_DELTA` reducer **复用**，不新建 merge 逻辑  

### 14.4 Phase 5 可选：WebSocket

若 500ms poll 仍觉慢或 HTTP 开销大，可加 `WS /world-stream` 推送 `{ through_tick, delta }`；**非 P0**。

---

## 十五、软引导文件索引（调 Agent 行为看这里）

以下均为 **软引导**（改文案/参数即可，非 L3 硬控）。按 **进入 Prompt 的顺序** 排列。

### 15.1 System Prompt — Soul / 目标 / 状态（PerceptionBuilder）

| 文件 | 改什么 |
|------|--------|
| [`agent_world/hbm_demo/hbm_scenario.yaml`](agent_world/hbm_demo/hbm_scenario.yaml) | 每个 Agent 的 **`soul`**、**`long_term_goal`**、**`current_state`**（# Soul 等五段 system） |
| 同上 `places[].attrs.behavior_hint` | **# Place Behavior Rule**（地点行为提示） |
| [`agent_world/hbm_demo/core/runner/kernel.py`](agent_world/hbm_demo/core/runner/kernel.py) | `segment_headers` 中文段标题（一般不改内容） |

### 15.2 User Prompt — L6 玩家句与角色约束

| 文件 | 改什么 |
|------|--------|
| [`features/f07_agent_control/player_response.py`](agent_world/hbm_demo/features/f07_agent_control/player_response.py) | **L6 主文件**：`format_l6_player_directive`（inject 目标）、`format_notification_directive`（非 inject primary）；Phase/Agent 专属 bullet（`_phase_agent_extra`） |
| [`features/f05_story_routing/routing.py`](agent_world/hbm_demo/features/f05_story_routing/routing.py) | `format_inject_dialogue` → 调用 L4+L6 组装 inject 文本 |

### 15.3 User Prompt — L4 知识库（Story Bible）

| 文件 | 改什么 |
|------|--------|
| [`features/f07_agent_control/story_knowledge/shared/phase_1.yaml`](agent_world/hbm_demo/features/f07_agent_control/story_knowledge/shared/phase_1.yaml) | Phase1 共享：`world_state`、`scene_atmosphere`、`plot_beats`、`forbidden_actions` |
| `.../shared/phase_2.yaml` ~ `phase_4.yaml` | 各 Phase 同上 |
| [`features/f07_agent_control/story_knowledge/agents/agent_1.yaml`](agent_world/hbm_demo/features/f07_agent_control/story_knowledge/agents/agent_1.yaml) | Agent1：`identity`、`speech_style`、`player_stance`、`relationships`、`phase_overrides`（含 `example_lines`、`response_checklist`） |
| `.../agents/agent_2.yaml` ~ `agent_7.yaml` | 各 Agent 角色 overlay |
| [`features/f07_agent_control/story_knowledge/turn_hints.yaml`](agent_world/hbm_demo/features/f07_agent_control/story_knowledge/turn_hints.yaml) | **按 Turn 1–25** 的「本 Turn 剧本参考」 |
| [`features/f07_agent_control/knowledge.py`](agent_world/hbm_demo/features/f07_agent_control/knowledge.py) | L4 **组装逻辑**；`format_session_facts`（含 Stats 门槛文案 — v2 应删）；`build_agent_knowledge` / `build_notification_snippet` |
| [`features/f07_agent_control/inject_batch.py`](agent_world/hbm_demo/features/f07_agent_control/inject_batch.py) | 非 inject primary 的 **短 notification** 路径 |

**v2 新增（待建）**：`knowledge.build_thread_recap()` — 近期对话/OS 摘要（§6.3）

### 15.4 User Prompt — 运行时短规则尾段

| 文件 | 改什么 |
|------|--------|
| [`core/runner/hbm_agent.py`](agent_world/hbm_demo/core/runner/hbm_agent.py) | `_hbm_short_action_rules()`：【本回合行动要求】尾段；Phase/角色 bullet（与 L6 有重叠，实施 v2 时应 **软化/去重**） |

### 15.5 L2 — 温度与长度

| 文件 | 改什么 |
|------|--------|
| [`features/f07_agent_control/turn_control.yaml`](agent_world/hbm_demo/features/f07_agent_control/turn_control.yaml) | `llm_params`：`Phase 1`、`Phase_1_passive`、`Phase 2`… 的 **temperature / max_tokens** |
| [`features/f07_agent_control/llm_params.py`](agent_world/hbm_demo/features/f07_agent_control/llm_params.py) | 解析与 passive 降温逻辑 |
| [`hbm_scenario.yaml`](agent_world/hbm_demo/hbm_scenario.yaml) `llm:` | 全局默认 model / temperature / max_tokens（Agent 级可覆盖） |

### 15.6 引擎 Observation（非 YAML，但影响 Agent 看到什么）

| 文件 | 改什么 |
|------|--------|
| [`agent_world/world/perception.py`](agent_world/world/perception.py) | 增量 observation：新私信、F2F feed、同室、feeds、移动 diff（一般少改；结构性行为） |

### 15.7 软引导 vs 硬控 — 勿与下列混淆

| 文件 | 性质 | 说明 |
|------|------|------|
| `features/f07_agent_control/pick_active.py` + `turn_control.yaml` `phases` | **硬 L3** | 谁 tick，不是说什么 |
| `features/f07_agent_control/tool_guard.py` | **硬（v2 应关）** | do_nothing 守卫 |
| `features/f07_agent_control/tool_matrix.yaml` | **硬（v2 应关）** | 工具白名单 |
| `features/f07_agent_control/f2f_fallback.py` | **硬（v2 应关）** | 模板替 Agent 说话 |

### 15.8 快速调参路径（常见需求）

| 想改… | 优先打开 |
|--------|----------|
| 前台怎么接待玩家 | `agent_1.yaml` + `player_response.py` Phase1 Agent1 段 + `phase_1.yaml` |
| Jensen 怎么 RDC VP | `agent_2.yaml` + `agent_3.yaml` + `phase_1.yaml` plot_beats |
| 某 Turn 剧情提示 | `turn_hints.yaml` 对应 Turn 键 |
| 口语长短 / 随机性 | `turn_control.yaml` llm_params + `hbm_scenario.yaml` llm |
| 角色根本人格 | `hbm_scenario.yaml` agents[].soul |
| 地点氛围 | `hbm_scenario.yaml` places behavior_hint + `phase_N.yaml` scene_atmosphere |
| **调试某条消息为何这样输出** | 点击该 **F2F/RDC/GRP/OS/地点** 行的 📝 → §十六 F15 |

---

## 十六、F15 Prompt Inspector — LLM 决策可追溯（开发工具 · R15）

### 16.1 目标

Demo 开发与调软引导时，需要回答：**「这条 F2F / RDC / GRP / 内心 OS / 地点变化，对应 Agent 当时发给 LLM 的完整 Prompt 是什么？」**

| 能力 | 说明 |
|------|------|
| **持久化** | 每次 Agent `perform_action_by_llm` 写入 **system + user** 全文及 tool 输出 |
| **关联** | 落库行为（三种消息、OS、移动）携带 **`prompt_trace_id`**，可反查 |
| **前端入口（唯一主路径）** | **点击** 消息气泡 / OS 行 / 地点记录行 → `PromptTraceModal` |
| **地点历史** | Agent 手机面板新增 **「地点记录」** 联系人行，逐条展示 `from → to @ tick` |

**不做**：左栏 **「Prompt 日志」** 全局列表按钮——Prompt 应从 **世界里的具体行为** 点进去看，而不是另开一套日志页。

**可选（仅后端）**：`GET /api/prompt-traces?…` 供脚本/curl 批量排查；**首版不做** 对应 UI。

**性质**：**开发/调试工具**，不改变 Agent 控制逻辑；生产可 `prompt_trace.enabled: false` 关闭写入。

### 16.2 现状缺口

| 项 | 现状 |
|----|------|
| Prompt 落库 | ❌ `hbm_agent.py` 仅内存调用 LLM，**无** trace 表 |
| 消息反查 | ❌ `GameMessage` / delta **无** `prompt_trace_id` |
| 地点历史 UI | ⚠️ `location_changes` 已在 F12 delta，但 **仅** 用于圆点动画 `recentMoveKeys`；**未** 写入 Agent inbox |
| OS 反查 | ⚠️ `osLog` 有内容，**无** trace 链接 |
| `do_nothing` 决策 | 无 outward 消息；**不提供** UI 入口（可 curl 列表 API，非 P0） |

### 16.3 数据模型（Runner · world.db）

#### 表 1：`agent_llm_trace`

每次 LLM 决策一行（在 `chat.completions.create` **之前** 写入 draft，**之后** 补全 tool 结果）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | TEXT PK | UUID，如 `tr_abc123` |
| `agent_id` | INT | 决策 Agent |
| `at_tick` | INT | 世界 tick `t` |
| `phase` | TEXT | turn_context.phase 快照 |
| `player_turn` | INT | 快照 |
| `model` | TEXT | 如 `deepseek-v4-flash` |
| `temperature` | REAL | 实际使用值 |
| `max_tokens` | INT | 实际使用值 |
| `system_prompt` | TEXT | PerceptionBuilder 完整 system |
| `user_prompt` | TEXT | `_observation_to_text` 完整 user |
| `tool_calls_json` | TEXT | LLM 返回的 tools（JSON 数组） |
| `assistant_content` | TEXT | 可选：纯文本 thought |
| `created_at` | TEXT | ISO 时间 |

#### 表 2：`agent_action_trace_link`

行为 outcome → trace 多对一（一条 trace 通常链 1 个主 outcome）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `link_id` | TEXT PK | UUID |
| `trace_id` | TEXT FK | → `agent_llm_trace` |
| `agent_id` | INT | 行为所属 Agent |
| `at_tick` | INT | 行为 tick |
| `link_kind` | TEXT | `f2f` \| `rdc` \| `grp` \| `state` \| `location` \| `do_nothing` \| `relation` |
| `ref_key` | TEXT | 稳定查找键，见 §16.4 |

**索引**：`(agent_id, at_tick)`、`trace_id`。

**配置**（`turn_control.yaml` 或 `world_loop.yaml`）：

```yaml
prompt_trace:
  enabled: true              # Demo 默认开；CI 可关
  max_traces_per_session: 5000
  truncate_prompt_chars: 0   # 0=不截断；过大时可设 32000
```

### 16.4 关联键 `ref_key` 约定

dispatch 落库后，Runner 写 link 行：

| link_kind | ref_key 格式 | 示例 |
|-----------|--------------|------|
| `f2f` | `f2f:{place_id}:{at_tick}:{sender_id}` | `f2f:nvidia_reception:42:1` |
| `rdc` | `rdc:{at_tick}:{sender_id}:{recipient_id}` | `rdc:42:1:2` |
| `grp` | `grp:{at_tick}:{sender_id}:{group_id}` | `grp:43:2:100` |
| `state` | `state:{at_tick}:{agent_id}:{hash8}` | content hash 前 8 位 |
| `location` | `loc:{at_tick}:{agent_id}` | `loc:44:2` |
| `do_nothing` | `noop:{at_tick}:{agent_id}` | 无 outward 行为时仍保留 trace |

**F2F 房间气泡 / 手机 RDC·GRP·OS / 地点行** 的 delta payload 增加可选字段：

```typescript
prompt_trace_id?: string;
ref_key?: string;
```

F12 `format_*` 在构建 message/state/location 时从 link 表或 dispatch 上下文填入。

### 16.5 Runner 写入点

```text
HbmAgent.perform_action_by_llm(t):
  1. build system + user
  2. INSERT agent_llm_trace (trace_id=新 UUID)
  3. LLM call
  4. UPDATE tool_calls_json / assistant_content
  5. dispatch tools
  6. 对每个 outcome INSERT agent_action_trace_link

fallback 模板 F2F（v2 已禁用）不写 trace。
scripted notify（E3 已禁用）不写 trace。
Flask IPC MOVE：link_kind=location, source=ipc_move，**无** LLM trace（UI 显示「系统移动 · 无 Prompt」）。
```

**实现文件（待建/改）**：

- `features/f15_prompt_trace/store.py` — DB CRUD  
- `core/runner/hbm_agent.py` — 挂钩 trace 写入  
- `core/runner/world_step.py` 或 dispatcher hook — outcome link  
- `persistence/world_db.py` — schema migration  

### 16.6 Flask API

| 方法 | 路径 | 行为 |
|------|------|------|
| `GET` | `/simulations/{sim_id}/prompt-trace/{trace_id}` | 返回完整 trace |
| `GET` | `/simulations/{sim_id}/prompt-trace/by-ref?ref_key=` | **UI 主路径** |
| `GET` | `/simulations/{sim_id}/prompt-traces?…` | **可选 · 仅后端** |

响应示例：

```json
{
  "trace_id": "tr_abc123",
  "agent_id": 1,
  "at_tick": 42,
  "phase": "Phase 1",
  "player_turn": 3,
  "model": "deepseek-v4-flash",
  "system_prompt": "# Soul\n…",
  "user_prompt": "# 玩家/系统注入…",
  "tool_calls": [{"name": "speak_to_local", "args": {}}],
  "links": [{"link_kind": "f2f", "ref_key": "f2f:nvidia_reception:42:1"}]
}
```

模块：`features/f15_prompt_trace/handler.py`，注册于 `routes.py`。

### 16.7 前端 UI

#### 16.7.1 点击反查 Prompt（唯一 UI 入口）

凡 **Agent 行为产生** 且在 UI 可见的记录，增加 **可点击**「查看 Prompt」入口（小图标 `📝` 或行内链接）：

| UI 位置 | 覆盖类型 | 组件 |
|---------|----------|------|
| WorldStage 房间 **F2F 气泡** | F2F | `AgentEphemeralBubble` / 房间历史 |
| Agent 手机 **RDC 气泡** | RDC | `MessageBubble` |
| Agent 手机 **GRP 气泡** | GRP | `MessageBubble` |
| Agent 手机 **内心 OS 时间线** | state | `InnerOsTimeline` 每一行 |
| Agent 手机 **地点记录**（新） | location | `LocationHistoryTimeline`（§16.7.2） |
| 世界事件弹窗 | 仅当链到 trace 时 | `WorldEventModal`（IPC 路由通常 **无** Prompt） |

**无可见落库行为时**（如 `do_nothing`、被 skip 的 tick）：**不强行做 UI**；需要时用 API/curl 或 Runner 日志排查。

**交互**：

```text
点击 → GET /prompt-trace/by-ref?ref_key=…
  → 打开 PromptTraceModal（全屏或侧栏）
      ├─ 元信息：Agent / tick / Phase / model / temperature
      ├─ Tab「System」只读 Markdown/纯文本
      ├─ Tab「User」只读
      └─ Tab「Tools」JSON 格式化 tool_calls
```

`GameMessage` / `StateChange` / `LocationChange` 类型扩展：

```typescript
prompt_trace_id?: string;
ref_key?: string;
```

Store：`applyWorldDelta` 保留上述字段；merge 时不去掉。

#### 16.7.2 Agent 地点变更历史（手机面板）

**现状**：`agent_location_log` 已落库；delta 有 `location_changes`，但 **未** 进入 Agent 手机 UI。

**目标**：每个 Agent 手机联系人列表增加一行：

```text
📍 地点记录          最后：谈判室 @ tick 44
```

点击进入 **地点时间线**（类似内心 OS）：

```text
tick 44  私密会议室 → 谈判室  （request_move / ipc_move）
tick 8   谈判室 → 私密会议室    （ipc_move）
```

**数据**：

- `AgentInbox` 扩展：`locationLog: LocationChange[]`（与 `osLog` 并列）  
- `applyWorldDelta`：`mergeLocationChanges(agentInbox, delta.location_changes)` — 按 `agent_id` 分流、按 `at_tick` 排序去重  
- `buildContactThreads` 增加 `kind: "location"` 线程，`title: "地点记录"`  
- 每一行可点击 → Prompt 反查（若 `source` 为 agent `request_move` 且有 trace；**IPC MOVE 无 Prompt**，显示说明文案）

**展示 copy**：

| source | 行文案 |
|--------|--------|
| `ipc_move` | `系统安排 · {from} → {to}` |
| `request_move` | `自主移动 · {from} → {to}` |
| `script` | `剧本 · {from} → {to}` |

地点名用 `placeDisplayName()` 中文。

### 16.8 与 F14 / F12 关系

- F14 delta **携带** `prompt_trace_id` / `ref_key` 字段 → 前端 merge 后即可点击  
- F12 formatter 扩展：`format_f2f_history_with_ids`、`format_messages`、`format_state_changes`、`format_location_changes`  
- **不要求** 每条 delta 拉全量 Prompt 正文（体积大）；点击时再 `GET /prompt-trace/{id}`

### 16.9 验收标准

- [ ] Agent1 发 F2F 后，**点击房间气泡** → Modal 展示 **完整 system+user**  
- [ ] **点击** RDC / GRP 气泡 → 同上  
- [ ] **点击** OS 行 → 同上  
- [ ] **点击** 地点记录行 → 有 trace 则展示；IPC MOVE 显示「无 Prompt」说明  
- [ ] 左栏 **无**「Prompt 日志」按钮；Prompt **仅**从消息/记录进入  
- [ ] `prompt_trace.enabled: false` 时隐藏 📝，不写 DB  

### 16.10 实施阶段

并入 **Phase 3**（与 L4 recap 同期，依赖 trace 稳定）：

- [ ] DB schema + `f15_prompt_trace` Runner 写入  
- [ ] Flask API 三端点  
- [ ] F12 delta 字段 + `mergeLocationChanges` + `locationLog`  
- [ ] `PromptTraceModal` + **消息/OS/地点行** 点击挂钩（**无** StatusPanel 全局按钮）  
- [ ] `AgentPhoneModal` 地点记录线程  

**可选 Phase 3b**：Runner 本地 `sim/prompt_traces.jsonl` 镜像（便于无 Flask 调试）。

---

## 十七、落地审查（v2.4 · 深度）

### 17.1 能否完整落地？

**结论：可以完整落地**，方案与产品诉求一致，且 F12 UI、L3、world.db 日志表等 **已有基础**。  
但当前 **代码 ≈0% v2**；按 Phase 0→4 顺序实施约 **4–6 个 PR**，每 Phase 有明确验收。

| 维度 | 评估 |
|------|------|
| 架构自洽 | ✅ 常驻 loop + 入队 inject + F14 poll + L3-only 硬控 闭环 |
| 与引擎兼容 | ✅ 不修改 `WorldStep` 语义，仅 HBM 编排层重构 |
| 与 F12 兼容 | ✅ delta merge 可复用；需 session 级 endpoint |
| 风险可控 | ⚠️ LLM 成本、路由 NL 误判、session 双写 — 有缓解项 |
| 文档可施工 | ⚠️ 下文 6 项需在编码前定稿（§17.2） |

### 17.2 实施前仍须定稿的 6 项（原 §13.3 升格）

#### ① Tick 节拍 — **已定稿 · 节拍 A**（无需产品决策）

```python
# world_loop.py 伪代码
while running:
    if paused: await pause_event.wait()
    drain_player_queue()
    await world_step.run_one_tick()   # 可能 3–15s（并行 LLM）
    write_env_status(...)
    await asyncio.sleep(tick_interval_sec)  # 默认 1.0s，在 tick 结束之后
```

**禁止**固定墙钟叠加 tick（会并发写 world.db）。  
**参数**：`tick_interval_sec = 1.0`（写 `turn_control.yaml` → `world_loop` 段）；LLM 慢时实际间隔 = tick 耗时 + 1s。

#### ② Flask Session ↔ Runner 镜像 — **已定稿**（v2.5 · 代理决策）

**你无需再选方案**：Flask session 已是权威源；Runner 只需一份 **只读快照 + 入队通道**。定稿如下。

**Mirror  payload**（≈ 现有 `build_turn_context()` + Runner 字段）：

```python
{
  "phase": "Phase 1",
  "player_turn": 5,           # 与 HbmSession 同步
  "place_id": "place_ceo_office",
  "stats": { "vision": 12, ... },
  "inject_agent_ids": [1, 2, 3],
  "llm_params": { ... },      # resolve_llm_params(phase, player_turn)
  "player_text": "",          # silent tick 为空；inject 批次用 queue 项内冻结的 text
  "player_inject_tick": 42,   # 上次 drain 玩家输入时的 world tick（L3 inject_exclusive）
}
```

**IPC**（`commands.py` 扩展）：

| 命令 | 谁发 | 作用 |
|------|------|------|
| `UPDATE_SESSION_MIRROR` | Flask | 替换 Runner 内 `SessionMirror`（RESET / 路由 / POST 后） |
| `ENQUEUE_PLAYER_INPUT` | Flask | 入队 `{ events, turn_context_frozen, broadcast? }`，下一 tick 边界 drain |
| `GET_LOOP_STATUS` / `PAUSE_LOOP` / `RESUME_LOOP` | Flask | F13 |

**同步时机**（Flask 写 session **之后** 立刻 IPC）：

1. **RESET / 开局** → `UPDATE_SESSION_MIRROR`（全量 bootstrap）  
2. **POST player-turn** → F04 打分 → `build_turn_context(session, text)`（**冻结 Turn N**）→ `ENQUEUE_PLAYER_INPUT` → session `player_turn += 1` → `UPDATE_SESSION_MIRROR`（Turn N+1，供 silent tick）  
3. **apply_routing** 改 phase/place/stats → 写 session → `UPDATE_SESSION_MIRROR`  

**Runner 每 tick**（Orchestrator）：

```text
mirror = session_mirror.latest()
world_step.set_tick_context(mirror)
drain_player_queue()          # inject 项自带冻结 turn_context（Turn N）
await world_step.run_one_tick()
```

**无 mirror 时**（Runner 刚启动、尚未收到 IPC）：

- **禁止** `super()._pick_active()` 全员 fallback（现有 `world_step.py` L81–82 行为在 v2 删除）  
- 使用 **bootstrap 默认**：`Phase 1 / turn 1 / DEFAULT_PLACE / INITIAL_STATS / primary_active`  
- Flask 在 `is_runner_ready` 后 **主动 push 一次** `UPDATE_SESSION_MIRROR`，缩短 bootstrap 窗口  

**权威原则**：`HbmSession`（Flask cookie）是唯一真相；Runner mirror 只消费、不反写 player_turn。

#### ③ Routing v2 落点（修正 §13.3 E）

**不在 Runner 内嵌完整 `apply_routing`**（避免 Flask session 与 IPC 自调用混乱）。

**定稿**：

```text
Flask 后台 RoutingWatcher（或 F14 poll 后同一线程）:
  每 env.current_tick 变化（或每 5 tick）:
    读 world.db + flask session
    若 node_a/b/c 满足 → send_move_agent + 更新 session
    PlaceMutation → ENQUEUE_SCRIPT_EVENT（入 Orchestrator 队列，不 send_inject_batch(tick_count)）
    写 routing_info 供 F12 world_events delta
```

**Phase 4** 再换 `agent_driven` 信号；**删除** `apply_routing` 内 `send_inject_batch(..., tick_count=)`。

#### ④ `POST /player-turn` 响应契约（原未写）

```json
{
  "success": true,
  "data": {
    "accepted": true,
    "stats_update": { "vision": 12, ... },
    "player_turn": 4,
    "current_phase": "Phase 1"
  }
}
```

- **无** `task_id`、`processing`、`completed`  
- F04 `immediate_msg`：保留占位或改由 **首条 F2F delta** 替代（二选一，首版可保留占位）  
- Turn 25 / `game_over`：仍 **同步** 特殊路径；触发后 **`PAUSE_LOOP` + 停止 F14 poll**

#### ⑤ `experience_hardening` 配置收敛

v2 **定稿**：

```yaml
experience_hardening:
  enabled: false          # 关闭 E1/E2/E3/fallback 总开关
  # inject_exclusive 改由 turn_control.phases + pick_active 读取，不依赖 hardening
```

`pick_active` 中 `inject_exclusive_ticks_for()` **改为**读 `turn_control.phases` 或独立 `world_loop.inject_exclusive`，**不再**绑定 `is_experience_hardening()`。

#### ⑥ F15 `ref_key` 与同 tick 多消息

同 tick 同 Agent 连发两条 RDC 时，`rdc:{t}:{sender}:{recipient}` 可能碰撞。

**定稿**：ref_key 追加 **`:{msg_id}`** 或 **`:{seq}`**（dispatch 返回 insert rowid）；F12 formatter 写入 delta。

### 17.3 文档/internal 已修正项（v2.4）

| 项 | 处理 |
|----|------|
| 重复「分支/下一步」页脚 | 已删 |
| Phase 3 仍写 Prompt 浏览器 | 已改 |
| §3.2 仍返回 task_id | 已改 |
| API 路径写 `/api/...` | 已改为 `/simulations/{sim_id}/...` |
| §8.2 Observer | 已改为 WorldStage/手机 |
| §13.3 G 说 §10.2 仍写 processing | §10.2 已改，G 可归档 |

### 17.4 各 Phase 落地依赖链（不可跳步）

```text
Phase 0 ──► 关 hard_block；否则 loop = 高频 do_nothing
    │
Phase 1 ──► Orchestrator + Queue + SessionMirror + pick_active 改造
    │         （无 Phase 0 勿开 loop）
    │
Phase 1b ─► pause/resume（依赖 Phase 1 loop）
    │
Phase 2 ──► F14 poll + player-turn 契约 + 废弃 task/completed
    │         （依赖 Phase 1 tick 常驻）
    │
Phase 3 ──► recap + F15 trace + locationLog UI
    │
Phase 4 ──► agent_driven routing + RoutingWatcher 改造
```

### 17.5 测试与回归（实施时必须并行）

| 范围 | 动作 |
|------|------|
| `test_m0_acceptance.py` | Phase 0 改 E1/E2/fallback 断言；新增 v2 loop smoke |
| `test_f12_*` | F14 session delta、locationLog merge、prompt_trace_id 字段 |
| 手玩清单 | dev_logs/19 参考台词 × Phase1→2；pause/resume；静默期 RDC 上 UI |
| dev_logs/30 | 文首加注「批模式已被 31 v2 取代」 |

### 17.6 仍属 P3 可选、不阻塞落地

- WebSocket delta（§14.4）  
- `story_advance` tool（§Phase 5）  
- `idle_pause_after_sec` 省电  
- `GET /prompt-traces` 列表 UI（§十六 已明确不做）  
- prompt jsonl 镜像（§16.10 可选）

### 17.7 R1–R15 落地信心（v2.4）

| 需求 | 信心 | 阻塞项 |
|------|------|--------|
| R1–R4 | 高 | Phase 0 |
| R5–R6 | 高 | Phase 1 + §17.2 ①② |
| R7 | 高 | Phase 0 + F12 已有 |
| R8 | 中 | Phase 0 MOVE no-op + Phase 4 routing |
| R9 | 高 | Phase 3 |
| R10 | 中 | Phase 4 NL 信号设计 |
| R11–R12 | 高 | Phase 1 L3 改造 |
| R13 | 高 | Phase 1b |
| R14 | 高 | Phase 2 |
| R15 | 高 | Phase 3 + §17.2 ⑥ |

**总评**：方案 **可完整落地**；无架构性死结。最大工程量是 **Phase 1（Orchestrator + session 镜像 + 废弃 inject 批）** 与 **Phase 2（前端双轨改单轨 poll）**，不是 Prompt/recap 本身。

---


