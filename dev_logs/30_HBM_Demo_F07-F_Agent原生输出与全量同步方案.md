# 开发日志 30：HBM Demo F07-F — Agent 原生输出、Agent 驱动路由与全量世界同步

**记录时间**：2026-05-24  
**状态**：方案（待实施）  
**前置文档**：

- [`dev_logs/24_HBM_Demo_Agent行为控制整合方案.md`](24_HBM_Demo_Agent行为控制整合方案.md) — F07 ABCS、Phase 行为、知识库
- [`dev_logs/29_HBM_Demo_F07_体验补强方案.md`](29_HBM_Demo_F07_体验补强方案.md) — F07-E 体验补强（E0–E6）
- [`dev_docs/1_story_prototype.md`](../dev_docs/1_story_prototype.md) — 剧情原型
- [`dev_docs/2_architecture.md`](../dev_docs/2_architecture.md) — API / Stats / 读库规范
- [`dev_logs/03_Web端Demo游玩形式与UI设计方案.md`](03_Web端Demo游玩形式与UI设计方案.md) — 三栏 UI 原始愿景

**关联 Feature**：`F07-F`（Agent 原生体验 + 路由 2.0）、`F12`（全量世界事件同步与前端展示）

---

## 一、背景与问题陈述

### 1.1 人工体验反馈（2026-05-24）

玩家在本地 Demo 实测中发现：

1. **前台回复极度模板化**：仅提取玩家关键词（如 `80%`、`KV`），套固定句式「您提到的{kw}，我需要跟黄总确认，请稍等。」
2. **其他 Agent 表现类似**：Observer 中黄仁勋对 Tech VP 的 RDC 高度重复。
3. **World Tick 与 UI 严重不匹配**：后台 `current_tick` 已达 24，中屏/Observer 仅有少量前台 + Jensen 相关内容。
4. **不符合产品预期**：用户希望 **所有 Agent 均由 LLM 自行输出**，不要用硬编码规则替 Agent 说话；Phase 切换应由 **Agent 判断与行为链** 驱动，而非单纯数值门槛。

### 1.2 根因摘要（代码审计结论）

| 现象 | 根因 | 层级 |
|------|------|------|
| 前台模板句 | `f2f_fallback.py` 批末 **scripted F2F** 写入 | F07-E1 |
| LLM 从未成功 F2F | `first_action_guard` 将非法 tool 整批替换为 `do_nothing` | F07-E1 |
| Jensen 绕过前台链 | `notify_jensen_player_summary` 直接注入玩家全文 | F07-E3 |
| Jensen RDC 重复 | RDC quota 在并行 tick 下可能被突破；E3 加剧 | F07-E2 |
| Tick 多、UI 少 | 每 Turn 12 tick inject + **API 只暴露部分 channel/place** | F03 + F11 + UI |
| Phase 与 Agent 决策脱节 | `node_a/b/c` 绑 Turn 编号 + Stats 阈值 | F05 |

**审计样本**（`sim/hbm_memory_war/world.db`，2 Turn）：

```text
F2F@reception tick12: 「您提到的80%，我需要跟黄总确认，请稍等。」  ← 与 fallback 模板逐字一致
F2F@reception tick24: 「您提到的KV，我需要跟黄总确认，请稍等。」
RDC@negotiation_room: 5 条，全部 sender=2 recipient=3，无 Agent1→2
```

---

## 二、现状机制详解

### 2.1 每 Turn 流水线

```text
POST /player-turn
  ├─ F04 score_player_turn()           → vision/execution/trust/burnout delta
  ├─ F02 check_turn4_bad_end()         → Stats 不足 → game_over + 硬编码保安台词
  ├─ F11 async inject (12 tick)        → F07 pick_active / tool_guard / LLM
  │     └─ 批末 apply_batch_f2f_fallback()  → 模板 F2F（若 LLM 未产出）
  ├─ F05 apply_routing()               → 节点 A/B/C（Stats + Turn + 少量 DB）
  └─ player_turn += 1
```

前端 F11-C 轮询 `GET /action-result?since_tick=` 合并 delta。

### 2.2 Phase 切换：当前是否依赖数值？

**是。** 除节点 B 需 world.db 中 VP→Jensen 正面 RDC 外，其余 gate 均以 **Turn 编号 + Stats** 为主。

| 节点 | 代码位置 | 触发条件 | 动作 |
|------|----------|----------|------|
| **Bad End** | `inject.py` `check_turn4_bad_end` | Turn=4 且 `V+E<15` | 不 inject；返回 stub F2F |
| **A → Phase 2** | `routing.node_a_applies` | Turn=4 且 `V+E≥15` | Jensen MOVE → `jensen_private_room` |
| **B → Phase 3** | `routing.node_b_applies` | Turn=12、Phase2、`E≥20`、Phase2 以来 VP→Jensen 正面 RDC | Jensen 回谈判室 + PlaceMutation |
| **C → Phase 4** | `routing.node_c_applies` | Turn=20、Phase3、`burnout<80` 且 `V≥30` | CEO 4/5/6 MOVE → reception |
| **D 结局** | `routing.resolve_ending_id` | Turn25 意图 LLM + `trust≥40/25` | 三结局 |

**与剧情原型的差距**：原型描述「前台判断 → 通报 Jensen → Jensen 与 VP 讨论 → 批准玩家进入私密会议室」，**当前实现中 Agent 对话不参与 A 节点**，仅 Stats 在 Turn 4 判定。

### 2.3 硬编码 / 非 LLM 输出清单（须移除或改造）

| 来源 | 文件 | 内容 |
|------|------|------|
| Scripted F2F fallback | `f2f_fallback.py` | Phase1/2/4 模板句 + `extract_player_keyword` |
| Bad End stub | `inject.py` `BAD_END_PUBLIC_MESSAGES` | 「保安，请这位先生离开。」 |
| Turn4 Stats gate | `inject.py` `check_turn4_bad_end` | 数值不足即 game_over |
| E3 Jensen 摘要 | `inject_batch.py` `notify_jensen_player_summary` | 玩家全文 notify 给 Agent2 |
| immediate_msg 占位 | `scoring.py` `IMMEDIATE_MSG_PLACEHOLDER` | API1 斜体即时反馈 fallback |
| Stats 启发式 | `scoring.py` `_heuristic_stats` | 关键词硬编码 delta |
| 路由 Turn 门槛 | `routing.py` `node_*_applies` | Turn 4/12/20 硬绑定 |

---

## 三、设计目标

1. **Agent 原生输出**：中屏 / Observer 可见内容 **100% 来自 LLM tool dispatch 落库**，无 scripted 替 Agent 发言。
2. **Agent 驱动路由**：Phase A/B/C/D 由 **world.db 行为信号** 触发；Stats **不参与 gate**（可保留展示）。
3. **全量世界同步**：前端能展示后台 world.db 中 **本 Turn 窗口内所有与剧情相关的事件**（见 §5）。
4. **保留 F07 软约束**：L3 活跃矩阵、L5 工具白名单、L4 知识库、L2 温度、L6 玩家句优先——但去掉与 LLM 冲突的硬兜底。

---

## 四、F07-F 后端修复方案

### 4.1 配置总开关

在 `turn_control.yaml` 或新建 `routing.yaml`：

```yaml
experience_hardening:
  enabled: true
  scripted_f2f_fallback: false      # F07-F：默认关闭模板 F2F
  jensen_player_summary_notify: false # F07-F：Phase1 关闭 E3 越权 notify

routing:
  mode: agent_driven                # legacy_stats | agent_driven
  stats_display_only: true          # Stats 仅展示，不 gate
```

`routing.mode: legacy_stats` 保留旧行为，便于 A/B 与回滚。

---

### 4.2 PR1 — 去除硬编码 Agent 输出（P0）

#### 4.2.1 关闭并移除 scripted fallback 主路径

| 改动 | 说明 |
|------|------|
| `turn_control.yaml` | `scripted_f2f_fallback: false` |
| `ipc_handlers.py` | 删除或 `#ifdef` 批末 `apply_batch_f2f_fallback_at` 调用 |
| `f2f_fallback.py` | 保留模块供单元测试/紧急回滚，默认不调用 |
| `completion.py` | `completed` 条件：**本批 inject 目标 Agent 的 LLM F2F 已落库**（`batch_guard.has_f2f` 且 `_f2f_source=llm`） |

**LLM F2F 保障（替代 fallback）**：

```text
Phase 1 inject 批内：
  Tick 0–3：仅 Agent1 tick（pick_active inject_exclusive 延长为 3）
  若 tick3 仍无 F2F：
    → 对 Agent1 触发 1 次「仅 speak_to_local」的低温补呼（max_tokens=120）
  仍失败 → inject_status=failed（前端显示错误），不写模板
```

建议 inject tick 总数：**12 → 8**（F2F 保障 tick + 2↔3 被动 + CEO 低频）。

#### 4.2.2 修订 E1 首动守卫 — 引导而非空转

**现状问题**：LLM 先选 `send_message` → 整批变 `do_nothing` → 12 tick 无 F2F → fallback。

**改法**（`tool_guard.py`）：

```text
若 required agent 尚未 F2F：
  - send_message / update_state / … → 改写为 speak_to_local
    content = 从 player_memory 或 send_message.args 提炼 1–2 句口语回应
  - 同批多 tool_calls：只替换非法项，不整批 do_nothing
  - 已有 F2F 后：send_message 正常走 quota + matrix
```

#### 4.2.3 关闭 Phase1 E3 越权 notify

- `inject_batch.notify_jensen_player_summary`：Phase1 **不再调用**。
- Jensen 仅通过 **Agent1→2 RDC** 或同批 notification snippet（无玩家 verbatim）获知访客。

#### 4.2.4 Bad End 改为 Agent 驱动

- 删除 `check_turn4_bad_end` 的 Stats 判定。
- 改为批后扫描：Agent1 F2F 含明确拒绝语义 **或** Phase1 超过 `max_turns_phase1`（如 10）且无 approve 信号 → `game_over`。
- `public_messages` 从 **world.db 该 Turn 的 Agent1 F2F** 读取，不用 `BAD_END_PUBLIC_MESSAGES` stub。

---

### 4.3 PR2 — RDC 链与 quota 修复（P1）

#### 4.3.1 BatchGuardState 并发安全

- `HbmWorldStep._batch_guard` 更新加 `asyncio.Lock`。
- quota 检查与 `mark_rdc` 在同一临界区。

#### 4.3.2 Phase1 tick 序（修订 E2）

```text
Tick 0–2：仅 Agent1（F2F 玩家 → 最多 1 条 RDC→2）
Tick 3–5：Agent2、3（Jensen 收 RDC 后与 VP 讨论，各 ≤ quota）
Tick 6–7：CEO 4/5/6 被动（仅 speak_to_local @ negotiation_room，短句）
```

`turn_control.yaml`：

```yaml
inject_exclusive_ticks:
  Phase 1: 3
rdc_quota_per_batch:
  Phase 1:
    1: 1   # 前台→Jensen
    2: 2   # Jensen→VP
    3: 1
```

#### 4.3.3 预期 Phase1 对话链（对齐 dev_logs/24）

```text
玩家 → [F2F] 前台 short reply
前台 → [RDC] Jensen「有人带…可能很重要」（非技术细节）
Jensen → [RDC] VP「去核实…」
VP → [RDC] Jensen「可行/需更多信息…」
Jensen → [RDC] 前台「带访客去私密会议室」  ← 节点 A 信号
前台 → [F2F] 玩家「请跟我来」
```

---

### 4.4 PR3 — Agent 驱动路由（P0）

新建 **`features/f05_story_routing/agent_signals.py`** + **`routing.yaml`**。

#### 4.4.1 节点 A：Phase 1 → Phase 2

**不再要求** Turn=4、`V+E≥15`。

**信号（批后扫 `world.db`，`since_tick=task.start_tick`）**：

| # | 条件 | 说明 |
|---|------|------|
| A1 | ∃ RDC **1→2** | 前台已简报 |
| A2 | ∃ RDC **2→3** | Jensen 已与 VP 讨论 |
| A3 | ∃ RDC **2→1** 且内容命中 approve 关键词 | `私密会议室\|可以见\|带进来\|批准` |
| 可选 A4 | ∃ F2F **1→0** @ reception 含「请跟我来\|这边请` | 前台对玩家确认 |

**动作**（与现节点 A 相同）：

- IPC `MOVE_AGENT` Jensen → `jensen_private_room`
- session：`phase=Phase2`，`place_id=jensen_private_room`，`phase2_start_tick=current_tick`

**Bad End 信号**（替代 Stats Turn4）：

- ∃ F2F 1→0 含 `拒绝|请离开|保安`
- 或 Phase1 连续 N Turn 无 A1 且玩家仍坚持（N 可配置，默认 8）

#### 4.4.2 节点 B：Phase 2 → Phase 3

**不再要求** Turn=12、`execution≥20`。

| 信号 | 条件 |
|------|------|
| B1 | ∃ F2F @ `jensen_private_room` sender=2（Jensen 对玩家认可/「回谈判室」） |
| B2 | ∃ RDC **3→2** 含正面关键词（沿用 `POSITIVE_RDC_KEYWORDS`） |

动作：Jensen MOVE 回 `negotiation_room` + PlaceMutation（保持现逻辑）。

#### 4.4.3 节点 C：Phase 3 → Phase 4

**不再要求** Turn=20、`vision≥30`、`burnout<80`。

| 信号 | 条件 |
|------|------|
| C1 | ∃ Jensen F2F/RDC 含「请离场\|谈完了\|出去」对 CEO |
| 或 C2 | ∃ GRP@200 三巨头停止进攻 + Jensen GRP@100 宣布散场 |

动作：CEO 4/5/6 MOVE → `nvidia_reception`；session `phase=Phase4`（保持现逻辑）。

#### 4.4.4 节点 D：Turn 25 结局

- 保留 `classify_turn25_intent`（LLM 读玩家最后一句话）。
- **去掉** `trust≥40/25` 硬门槛；改为 **Jensen 末轮 F2F 态度** + intent 联合（或 optional `story_advance` 工具）。

#### 4.4.5 可选：显式工具 `story_advance`（P2，稳定性补充）

```python
story_advance(signal: Literal[
  "approve_visitor", "reject_visitor",
  "return_to_negotiation", "expel_ceos",
  "offer_join", "offer_seed",
])
```

- LLM 自行调用；路由层 **只读 tool 落库记录**，减少自然语言误判。
- **不替 Agent 生成台词**——与 scripted fallback 有本质区别。

#### 4.4.6 `apply_routing` 改造伪代码

```python
def apply_routing(session, db, ...):
    if routing_mode == "agent_driven":
        if session.phase == "Phase 1" and detect_node_a(db, task):
            apply_move_jensen_private(...)
        elif session.phase == "Phase 2" and detect_node_b(db, task):
            apply_move_jensen_negotiation(...)
        elif session.phase == "Phase 3" and detect_node_c(db, task):
            apply_move_ceos_out(...)
    else:
        # legacy_stats：现有 node_a_applies 等
        ...
```

---

### 4.5 PR4 — Stats（F04）与 Prompt 清理

| 选项 | 行为 |
|------|------|
| **推荐** | `stats_display_only: true` — 继续 LLM 打分，左栏展示，**不参与任何 node** |
| 可选 | 完全关闭 `score_player_turn` 减 LLM 调用 |
| 知识库 | `knowledge.format_session_facts` 删除「距节点 A 还需 V+E≥15」类 Stats 提示 |
| turn_hints | 改为 Agent 目标描述，不绑 Stats |

---

## 五、F12 — 全量世界同步与前端展示（已审计 · 必须实施）

### 5.1 审计结论（2026-05-24 实测）

脚本：`agent_world/hbm_demo/scripts/test_message_visibility_gap.py`

**对当前玩家 world.db（2 Turn，Phase1 @ reception）**：

```text
Turn1 tick0–12: world_total=5 → api_visible=5（1 F2F + 4 RDC）hidden=0
Turn2 tick12–24: world_total=2 → api_visible=2 hidden=0
```

**说明**：该样本中 CEO 未产生 `negotiation_room` F2F，故 **尚未触发结构性缺口**；但 dev_logs/24 要求 CEO「偶尔同室短句」，一旦 LLM 产出则 **必然被隐藏**。

**合成场景验证**（脚本 `simulate_hidden_f2f_gap()`）：

```text
Phase1 CEO speak_to_local @ negotiation_room
→ visible_in_api: false
→ 当前 UI 无任何栏目可展示
```

### 5.2 当前 API → 前端映射（F03 / F11）

| 数据 | API 字段 | 前端 Store | UI 栏目 |
|------|----------|------------|---------|
| 玩家地点 F2F | `public_messages` | `f2fMessages` | 中屏 MainChat |
| 全局 RDC | `observer_messages` | `rdcMessages` | Observer Tab「私聊 RDC」 |
| 全局 GRP | `group_messages` | `grpMessages` | Observer Tab「群聊 GRP」 |
| **非玩家地点 F2F** | **未返回** | — | **不可见** |
| **update_state** | **未返回** | — | **不可见** |
| **IPC MOVE / Phase** | session 快照 | phaseToast / placeLabel | 仅 toast，无时间线 |
| **PlaceMutation** | **未返回** | — | **不可见** |
| **scripted_notification** | **未返回** | — | **不可见** |

读库逻辑（`handler.py` / `delta.py`）：

```python
# 中屏：仅 task.place_id 的 F2F
f2f_history = db.fetch_f2f_history_at(task.place_id, ...)

# Observer：全局 RDC / GRP（与 place 无关）
rdc_rows = db.fetch_messages_since(channel_type="RDC", ...)
```

**结论**：前端 **没有 bug**（正确渲染 API 所给数据）；**后端 API 故意过滤**，导致 world 变化无法全量展示。须扩展 API + UI（F12）。

### 5.3 F12 目标信息架构（对齐 dev_logs/03 上帝视角愿景）

```text
┌─────────────────────────────────────────────────────────────┐
│ 中屏 MainChat — 玩家可感知                                   │
│   • 玩家 place_id 的 F2F（含玩家 recipient=0）               │
├─────────────────────────────────────────────────────────────┤
│ Observer — 上帝视角（本 Turn 窗口 since_tick..end_tick）    │
│   Tab1 私聊 RDC      （现有）                                │
│   Tab2 群聊 GRP      （现有）                                │
│   Tab3 背景 F2F      【新增】非玩家地点 / 同室 Agent 对话     │
│   Tab4 内心 OS       【新增】update_state 摘要               │
│   Tab5 世界事件      【新增】MOVE / 广播 / Phase 切换        │
└─────────────────────────────────────────────────────────────┘
```

### 5.4 后端 API 扩展（F12-A）

#### 5.4.1 扩展 `TurnDelta` / `ActionResultCompleted`

```typescript
interface TurnDelta {
  public_messages: GameMessage[];       // 不变：玩家地点 F2F
  observer_messages: GameMessage[];     // RDC
  group_messages: GameMessage[];        // GRP
  background_f2f: GameMessage[];        // 【新】place_id != task.place_id 的 F2F
  agent_states: AgentStateEntry[];        // 【新】update_state 快照
  world_events: WorldEvent[];           // 【新】MOVE / broadcast / phase_change
  through_tick: number;
}
```

#### 5.4.2 `build_turn_delta` 改造（`delta.py` / `handler.py`）

```python
def build_turn_delta(...):
    # 现有 public / rdc / grp ...

    # background_f2f：本窗口所有 F2F，排除已在 public 中的 (place==task.place_id)
    all_f2f = db.fetch_f2f_all_since(since_t, t_now)  # 新 DB 方法
    background = [r for r in all_f2f if r.place_id != task.place_id]

    # agent_states：读 agent 表 current_state 变更（或新 state_log 表）
    agent_states = db.fetch_state_changes_since(since_t, t_now)

    # world_events：session 路由 + LIST_PLACES diff（或 IPC 路由写 event_log）
    world_events = load_world_events_for_task(task_id)
```

#### 5.4.3 Runner 侧：可选 `world_event_log` 表

在 `apply_routing` / `MOVE_AGENT` / `broadcast_place` 后写入：

```sql
INSERT INTO world_event_log (attempted_at, event_type, payload_json)
-- event_type: move_agent | phase_change | place_mutation | broadcast
```

Flask 只读，F12 delta 合并。

#### 5.4.4 `update_state` 暴露策略

引擎 `update_state` 写入 Agent 内存/DB，当前 **不在 `direct_message`**。

**方案（推荐）**：

- Runner dispatch `update_state` 成功后，追加一行 **`channel_type='STATE'`** 到 `direct_message`（sender=agent_id, content=新 state 摘要，place_id=当前地点）。
- Flask `format_messages` 识别 `STATE` → `agent_states` 数组。
- **不改引擎核心**：仅在 `HbmWorldStep._run_single_agent` dispatch 后 hook（与 E0 F2F hook 同级）。

### 5.5 前端改造（F12-B）

| 文件 | 改动 |
|------|------|
| `web/src/api/types.ts` | 扩展 `TurnDelta`、`ActionResultCompleted` |
| `web/src/store/gameStore.ts` | 新增 `backgroundF2fMessages`、`agentStates`、`worldEvents`；reducer merge |
| `web/src/features/observer/ObserverPanel.tsx` | 新增 Tab：背景 F2F / 内心 OS / 世界事件 |
| `web/src/utils/messages.ts` | `messageKey` 支持新 type |
| `web/src/features/layout/StatusPanel.tsx` | 可选：展示「在场 Agent」从 session/API 实时拉取 |

#### 5.5.1 增量合并

F11-C 现有 `APPEND_TURN_DELTA` 须合并新字段；`messageKey` 去重规则覆盖 `STATE` / `WORLD`。

#### 5.5.2 Phase / MOVE 展示

`world_events` 中 `phase_change` 除现有 `phaseToast` 外，在 Observer「世界事件」流写入：

```text
[tick 12] 路由节点 A：Jensen 进入私密会议室 · 玩家地点 → jensen_private_room
```

### 5.6 F12 验收标准

| # | 测试 | 通过条件 |
|---|------|----------|
| V1 | 注入 CEO F2F @ negotiation_room | Observer「背景 F2F」可见，中屏不出现 |
| V2 | Jensen update_state | Observer「内心 OS」可见 |
| V3 | 节点 A MOVE | 「世界事件」tab 有 move + phase 记录 |
| V4 | Turn16 broadcast | RDC sender=彭博终端 已在 Tab1；广播事件在 Tab5 |
| V5 | `test_message_visibility_gap.py` | `hidden_count==0`（扩展审计含 background_f2f） |
| V6 | 全 Turn E2E | `world_total == api_visible_total`（全 channel） |

---

## 六、文件改动清单（汇总）

### 6.1 后端

| 文件 | PR | 改动摘要 |
|------|-----|----------|
| `turn_control.yaml` | 1 | fallback off；exclusive_ticks；quota |
| `routing.yaml` | 3 | **新建** agent_driven / stats_display_only |
| `tool_guard.py` | 1 | 守卫改写 speak_to_local |
| `ipc_handlers.py` | 1 | 移除批末 fallback |
| `completion.py` | 1 | LLM F2F only complete |
| `inject_batch.py` | 1 | 关闭 Phase1 jensen summary |
| `inject.py` | 1+3 | Bad End agent-driven |
| `f2f_fallback.py` | 1 | 默认不调用；保留回滚 |
| `agent_signals.py` | 3 | **新建** 行为信号检测 |
| `routing.py` | 3 | apply_routing 双模式 |
| `world_step.py` | 1+2 | guard lock；STATE hook |
| `delta.py` / `handler.py` | 12 | 扩展 delta 字段 |
| `world_db.py` | 12 | fetch_f2f_all_since；fetch_state_changes |
| `batch_guard.py` | 2 | 文档 + lock 配合 |

### 6.2 前端

| 文件 | PR | 改动摘要 |
|------|-----|----------|
| `api/types.ts` | 12 | 新 delta 字段 |
| `gameStore.ts` | 12 | 新 state + reducer |
| `ObserverPanel.tsx` | 12 | 5 Tab |
| `messages.ts` | 12 | dedupe keys |

### 6.3 测试 / 脚本

| 文件 | 改动 |
|------|------|
| `scripts/test_m0_acceptance.py` | 更新断言：无 fallback 模板；agent 路由；F12 delta |
| `scripts/test_message_visibility_gap.py` | **已建**；扩展全 channel 审计 |
| `scripts/eval_f07_experience.py` | 拒绝模板句；验证 RDC 链 |

---

## 七、实施顺序与 PR 划分

```text
PR1 — F07-F 去硬编码 + E1 守卫改写（§4.2）
  • 无模板 F2F；LLM 补呼；Bad End 读库
  • 测试：F2F 内容不得匹配 fallback 正则

PR2 — RDC 链 + quota 锁（§4.3）
  • Phase1 1→2→3→1 链；quota 并发安全
  • 测试：每 Turn quota；存在 1→2 RDC

PR3 — Agent 驱动路由（§4.4）
  • agent_signals.py；routing.yaml；legacy 回滚
  • 测试：无 Stats 触发 Phase2；RDC 链触发 MOVE

PR4 — F12 全量同步（§5）
  • API delta 扩展 + Observer 新 Tab + STATE hook
  • 测试：test_message_visibility_gap 全绿；人工 CEO F2F 可见

PR5 — 文档 / turn_hints / eval 更新
  • dev_logs/19 参考台词备注「无 Turn4 硬门槛」
  • README 更新 Phase 切换说明
```

**依赖**：PR1 与 PR4 可并行；PR3 依赖 PR2（RDC 链是 A 节点信号源）。

---

## 八、风险与回滚

| 风险 | 缓解 |
|------|------|
| 去掉 fallback 后中屏偶发空 | Agent1 独占 tick + speak_to_local 补呼；processing 延长 |
| Agent 路由漏触发 | `routing.mode: legacy_stats` 双轨；`story_advance` 工具 |
| F12 API  breaking change | delta 新字段 optional；旧前端忽略 |
| STATE hook 侵入 Runner | 仅 HbmWorldStep hook，不改 agent_world 核心 dispatcher |
| CI flaky | 信号检测用 DB 结构断言；LLM 内容宽松关键词 |
| 回滚 F07-E | `experience_hardening.scripted_f2f_fallback: true` + `routing.mode: legacy_stats` |

---

## 九、总体验收标准（F07-F + F12）

### 9.1 Agent 原生输出

- [ ] Phase1 Turn1 中屏 F2F **不匹配** `/您提到的.+请稍等/` 模板
- [ ] world.db 本 Turn F2F **无** batch 末 tick 集中写入的单一模板（除非 LLM 真说类似话）
- [ ] Observer 存在 **Agent1→2** RDC，且先于 Jensen→3
- [ ] Phase1 玩梗 Turn：**无** 1→2 RDC；中屏 F2F 接梗（非「请黄总确认」）

### 9.2 Agent 驱动路由

- [ ] **无** Turn4 Stats Bad End；拒绝由 Agent F2F 表达
- [ ] Phase1→2：**无** V+E 要求；A1+A2+A3 信号满足即 MOVE
- [ ] Phase2→3：VP 正面 RDC + Jensen 认可 F2F，**无** Turn12/E≥20
- [ ] Phase3→4：CEO 离场信号，**无** Turn20/Vision/Burnout

### 9.3 全量世界同步

- [ ] CEO `negotiation_room` F2F 在 Observer「背景 F2F」可见
- [ ] Jensen `update_state` 在「内心 OS」可见
- [ ] 路由 MOVE 在「世界事件」可见
- [ ] `test_message_visibility_gap.py`：扩展后 `hidden_count==0`

### 9.4 平台回归

- [ ] `test_m0_acceptance.py` ALL PASS
- [ ] F11 增量 merge 含新字段无重复
- [ ] `npm run build` 成功

---

## 十、附录

### A. Phase 切换对照表（改造前 vs 改造后）

|  transition | 改造前 | 改造后（agent_driven） |
|------------|--------|------------------------|
| Phase1→2 | Turn4 且 V+E≥15 | 1→2 + 2→3 + 2→1 approve RDC |
| Bad End | Turn4 且 V+E<15 stub | Agent1 拒绝 F2F 或超时 |
| Phase2→3 | Turn12 且 E≥20 + VP RDC | Jensen F2F 认可 + VP 正面 RDC |
| Phase3→4 | Turn20 且 V≥30 且 burnout<80 | Jensen 驱离 CEO 信号 |
| 结局 | intent + trust 门槛 | intent + Jensen 末轮态度 |

### B. 相关代码索引

| Topic | Path |
|-------|------|
| Scripted fallback | `features/f07_agent_control/f2f_fallback.py` |
| First action guard | `features/f07_agent_control/tool_guard.py` |
| Jensen notify | `features/f07_agent_control/inject_batch.py` |
| Action result / delta | `features/f03_action_result/handler.py`, `features/f11_live_turn_sync/delta.py` |
| Routing nodes | `features/f05_story_routing/routing.py` |
| Stats scoring | `features/f04_stats/scoring.py` |
| Frontend store | `web/src/store/gameStore.ts` |
| Observer UI | `web/src/features/observer/ObserverPanel.tsx` |
| Visibility audit | `scripts/test_message_visibility_gap.py` |

### C. 可见性审计命令

```bash
# 玩家实测后，在仓库根目录：
python3 agent_world/hbm_demo/scripts/test_message_visibility_gap.py

# 完整回归（实施后）：
python3 agent_world/hbm_demo/scripts/test_m0_acceptance.py
```

---

**文档版本**：v1.0 · 2026-05-24  
**下一步**：按 PR1 → PR2 → PR3 → PR4 实施；实施前确认 `routing.mode` 默认值与 `scripted_f2f_fallback: false`。
