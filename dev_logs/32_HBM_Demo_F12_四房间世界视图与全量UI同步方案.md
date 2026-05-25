# 开发日志 32：HBM Demo F12 — 四房间世界视图与全量 UI 同步方案

**记录时间**：2026-05-25  
**状态**：方案（待实施）  
**分支**：`feature/f12-full-world-ui-sync`（从 `jensen-hwang-demo` @ `1963378`）  
**关联 Feature**：`F12`（全量世界同步 + 四房间 UI）

**前置文档**：

- [`dev_logs/30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md`](30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md) — API 扩展与 Observer 增强（本方案 UI 形态不同，API 方向一致）
- [`dev_logs/31_HBM_Demo_Runner控制层详解与引导式Agent方案.md`](31_HBM_Demo_Runner控制层详解与引导式Agent方案.md) — Runner 控制层与可见性缺口
- [`dev_logs/03_Web端Demo游玩形式与UI设计方案.md`](03_Web端Demo游玩形式与UI设计方案.md) — 原始三栏 UI 愿景
- [`dev_logs/28_HBM_Demo_F11_回合内增量同步方案.md`](28_HBM_Demo_F11_回合内增量同步方案.md) — delta 轮询机制

**关联代码**：

- Flask：`agent_world/hbm_demo/features/f12_world_sync/`（新建）
- Runner：`agent_world/hbm_demo/core/runner/`、`agent_world/world/dispatcher.py`、`agent_world/script/effects/place_mutation.py`
- 前端：`agent_world/hbm_demo/web/src/features/world-stage/`（新建）

---

## 一、目标与产品形态

### 1.1 用户可见的 UI 目标

| 区域 | 行为 |
|------|------|
| **左栏 StatusPanel** | **保持不变**：Stats、Phase/Turn、重开等 |
| **中栏 WorldStage** | **2×2 房间网格**，四格对应四个 `place_id` |
| **房间内 Agent** | 有 Agent 在场时显示 **可点击圆点**；玩家以固定圆点表示（随 `session.place_id`） |
| **房间内 F2F** | Agent 在该房间 F2F 发言时，房间格内出现 **短消息气泡**（非全屏聊天列表） |
| **Agent 圆点点击** | 弹出 **手机式消息面板**：私信 thread、群聊 thread、内心 OS 时间线 |
| **Agent 移动** | IPC MOVE / `request_move` 后，**圆点从原房间格移到目标房间格**（见 §五.4） |
| **世界广播/事件** | 屏幕 **居中弹窗**（WorldEventModal），如彭博快讯、Phase 路由、PlaceMutation |
| **右栏 Observer** | **取消**；RDC/GRP 改由 Agent 手机面板承载 |

### 1.2 技术目标

- Flask + Runner 协同，使前端能看到 **绝大部分** 后台世界变化，尤其是 **Agent 行为**。
- 不修改 F07 控制逻辑；Runner 改动限于 **持久化/日志** 与 **PlaceMutation 写 DB**。
- Demo 仍可 `run_hbm` + Flask + Web 正常跑通；`test_m0_acceptance` 回归通过。

---

## 二、现状缺口（为何必须改 Flask + Runner + 前端）

| 变化类型 | Runner/DB 有？ | 当前 Flask API | 当前 UI |
|----------|---------------|----------------|---------|
| 全 place F2F | DB 有 | 仅 `task.place_id` | 中栏列表，无房间视图 |
| RDC / GRP | DB 有 | 全量进 Observer | 右栏，无 per-agent |
| Agent 位置 | `agent_location` | 无 HTTP | 无圆点 |
| 移动事件 | 仅快照 | 无 | 无 |
| 内心 OS | 仅内存 `current_state` | 无 | 无 |
| PlaceMutation | 仅内存 attrs | 无 | 无 |
| 关系 / 群成员 | `relation` / `group_member` / `group_event` | 无 | 无 |
| 广播 | RDC sender=-1 | 混在 Observer RDC | 无独立弹窗 |

---

## 三、引擎事实（影响 Thread 与移动 UI）

### 3.1 关系断裂后还能私信吗？

**不能（新消息不可达）。** `ConnectivityResolver.phi_rdc` 依赖 `RelationGraph.contacts_of`；`relation_change break` 移除 contact 边后，新 RDC 写入 `delivered=0` 或无法送达。

**UI 策略（与群退一致）**：

- 历史私信 **永久保留**；
- 收到 `relation_remove` 事件时，thread 追加系统句：**「与对方关系已断裂」**；
- thread 标记为 `archived`，**不再 merge 新的 delivered=1 消息**。

### 3.2 退出群聊后还能收群消息吗？

**不能。** `leave_group` 移除 `group_member` 并清 pending GRP fan-out。

**UI 策略**：

- 历史群消息保留；
- 收到 `group_leave` 时追加：**「您已退出该群聊」**；
- 该群 thread 归档，之后无新消息。

### 3.3 Agent 移动的数据来源

| 来源 | 写哪里 | Flask 如何读 |
|------|--------|-------------|
| IPC `MOVE_AGENT`（F05 路由） | `agent_location` + **新表 `agent_location_log`** | delta `location_changes` |
| Agent `request_move`（step 9 commit） | 同上 | 同上 |
| Script `MoveEffect` | 同上 | 同上 |

前端收到 `location_changes` 或 snapshot 中 `agentLocations` 变化后，**将圆点从旧 RoomCell DOM 移到新 RoomCell**（§五.4）。

---

## 四、Runner 层改动（最小必要集）

> 原则：不改 F07 守卫/fallback；只补 **Flask 读不到** 的数据管道。

### 4.1 新表 DDL

路径建议：`agent_world/persistence/schema/world/`

**`agent_location_log.sql`**

```sql
CREATE TABLE IF NOT EXISTS agent_location_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     INTEGER NOT NULL,
    from_place   TEXT,
    to_place     TEXT NOT NULL,
    at_tick      INTEGER NOT NULL,
    source       TEXT NOT NULL  -- ipc_move | request_move | script | reset
);
CREATE INDEX IF NOT EXISTS idx_agent_location_log_tick
    ON agent_location_log(at_tick);
```

**`agent_state_log.sql`**

```sql
CREATE TABLE IF NOT EXISTS agent_state_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     INTEGER NOT NULL,
    content      TEXT NOT NULL,
    at_tick      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_state_log_agent_tick
    ON agent_state_log(agent_id, at_tick);
```

**`WorldDB` 扩展**（`agent_world/persistence/world_db.py`）：

- `insert_location_log(agent_id, from_place, to_place, at_tick, source)`
- `insert_state_log(agent_id, content, at_tick)`
- `fetch_location_logs_since(since_tick, t_now)`
- `fetch_state_logs_since(since_tick, t_now, agent_id=None)`

### 4.2 写入挂点

| 挂点 | 文件 | 动作 |
|------|------|------|
| IPC MOVE | `hbm_demo/core/runner/ipc_handlers.py` `handle_move_agent` | move 成功后 `insert_location_log(..., source='ipc_move')` |
| REQUEST_MOVE commit | `world/dispatcher.py` `commit_pending_moves` | 每次提交写 log，`source='request_move'` |
| Script MoveEffect | `script/effects/move.py` | 写 log，`source='script'` |
| UPDATE_STATE | `world/dispatcher.py` `_set_current_state` | 成功后 `insert_state_log` |
| StateChangeEffect | `script/effects/state_change.py` | 同上 |
| PlaceMutation | `script/effects/place_mutation.py` | **增加** `world_db.update_place_attrs(place_id, attrs_patch)`（当前仅内存） |
| RESET_WORLD | `hbm_demo/features/f01_session/world_reset.py` | 清空两 log 表 |

### 4.3 IPC `LIST_PLACES` Flask 封装

**文件**：`hbm_demo/http/ipc_helper.py`

```python
def fetch_list_places(ipc_client) -> dict:
    # CommandType.LIST_PLACES → { places, agent_locations }
```

**用途**：`world-snapshot` 在 DB 与 Runner 不一致时以 Runner 为准；可选每 Turn 完成校准一次。

### 4.4 Runner 改动不触及

- F07 `tool_guard` / `f2f_fallback` / `inject_batch`
- `HbmWorldStep` tick 编排
- Agent LLM prompt

---

## 五、Flask 层：Feature F12

### 5.1 模块结构

```
agent_world/hbm_demo/features/f12_world_sync/
├── __init__.py
├── delta.py           # build_world_delta — 核心
├── snapshot.py        # build_world_snapshot — 全量校准
├── formatter.py       # GameMessage / WorldEvent / SocialEvent
├── handler.py         # GET /world-snapshot（可选独立端点）
└── runner_bridge.py   # IPC list_places（校准用）
```

### 5.2 F06 读库扩展

**文件**：`features/f06_read_model/world_db.py` — `ReadOnlyWorldDB` 新增：

| 方法 | 说明 |
|------|------|
| `fetch_all_agent_locations()` | 全量 `{agent_id: {place_id, arrived_at}}` |
| `fetch_f2f_by_places(since_t, t_now, place_ids)` | 四房间 F2F |
| `fetch_rdc_for_agent(agent_id, since_t, t_now)` | 该 agent 收/发 RDC |
| `fetch_grp_for_agent(agent_id, since_t, t_now)` | 该 agent 仍为成员的群 GRP |
| `fetch_group_members()` | `{group_id: [agent_ids]}` |
| `fetch_group_events_since(since_t, t_now)` | join/leave/kick |
| `fetch_relations_snapshot()` | 全量 relation 边 |
| `fetch_broadcasts_since(since_t, t_now)` | `sender_id=-1` |
| `fetch_location_logs_since(since_t, t_now)` | 移动 log |
| `fetch_state_logs_since(since_t, t_now, agent_id?)` | OS log |
| `fetch_place_attrs(place_ids)` | place.attrs JSON |

### 5.3 API 响应形状

**主路径**：扩展 F11 `TurnDelta`，合并进 `GET /action-result`（不增加额外轮询）。

```typescript
interface TurnDelta {
  through_tick: number;
  player_place_id: string;

  // 四房间 F2F（取代原 public_messages）
  room_f2f: Record<PlaceId, GameMessage[]>;

  // per-agent 增量（手机面板）
  agent_messages: Record<AgentId, {
    rdc: GameMessage[];
    grp: GameMessage[];
  }>;

  // Agent 移动（驱动圆点换格）
  location_changes: LocationChange[];

  // 社交事件（群退/关系断 → 系统句 + thread 归档）
  social_events: SocialEvent[];

  // 内心 OS
  state_changes: StateChange[];

  // 世界事件（居中弹窗）
  world_events: WorldEvent[];

  // 全量 locations 快照（每 delta 附带，便于圆点绝对位置校准）
  agent_locations: Record<AgentId, { place_id: string; arrived_at: number }>;
}

interface LocationChange {
  agent_id: number;
  from_place: string | null;
  to_place: string;
  at_tick: number;
  source: "ipc_move" | "request_move" | "script";
}

interface WorldEvent {
  id: string;
  at_tick: number;
  kind: "broadcast" | "phase_route" | "place_mutation" | "bad_end" | "system";
  title?: string;
  content: string;
  place_id?: string;
}

interface SocialEvent {
  at_tick: number;
  kind: "relation_add" | "relation_remove" | "group_join" | "group_leave" | "group_kick";
  agent_id: number;
  peer_id?: number;
  group_id?: number;
  relation_type?: string;
}

interface StateChange {
  agent_id: number;
  content: string;
  at_tick: number;
}
```

**`status: completed`** 的 `ActionResultCompleted` 同样携带上述字段（全量 since `task.start_tick`）。

**可选**：`GET /api/hbm/simulations/{sim_id}/world-snapshot` — session 刷新与 Turn 完成后校准。

### 5.4 世界事件识别

| kind | 来源 |
|------|------|
| `broadcast` | `direct_message` 且 `sender_id=-1`（含 Turn16 彭博） |
| `phase_route` | F05 `apply_routing` 写入 `async_state/runtime.json` 的 `routing_info` |
| `place_mutation` | `place.attrs` diff 或 `script_event_log` |
| `bad_end` | Turn4 Bad End stub |
| `system` | inject 批边界、reset 等 |

### 5.5 改造现有文件

| 文件 | 改动 |
|------|------|
| `f11_live_turn_sync/delta.py` | 委托 `f12_world_sync.delta.build_world_delta` |
| `f03_action_result/handler.py` | completed/processing 均返回 F12 字段 |
| `f03_action_result/completion.py` | `format_messages` 增加 `agent_id`, `recipient_id`, `delivered` |
| `f05_story_routing/routing.py` | routing 后写 `routing_events` 到 runtime（供 world_events） |
| `http/routes.py` | 注册 world-snapshot；扩展 action-result 类型 |
| `features/__init__.py` | 注册 F12 |

### 5.6 GameMessage 扩展

```typescript
interface GameMessage {
  sender: string;
  content: string;
  type: "F2F" | "RDC" | "GRP";
  attempted_at?: number;
  sender_id?: number;
  recipient_id?: number;
  recipient?: string;
  group_id?: number;
  place_id?: string;
  delivered?: 0 | 1;
  is_system?: boolean;   // 群退/关系断/广播
}
```

---

## 六、前端层改动

### 6.1 布局：两栏 + 世界舞台

```
┌──────────┬─────────────────────────────────────────────┐
│ Status   │  WorldStage                                  │
│ Panel    │  ┌──────────────┬──────────────┐             │
│ (240px)  │  │ reception    │ jensen_room  │  2×2 grid   │
│          │  │  ○1 ○玩家    │  ○2          │             │
│          │  │  💬          │              │             │
│          │  ├──────────────┼──────────────┤             │
│          │  │ negotiation  │ openai_hq    │             │
│          │  │ ○2○3○4○5○6  │  ○7          │             │
│          │  └──────────────┴──────────────┘             │
│          │  PlayerInput（底部固定）                       │
└──────────┴─────────────────────────────────────────────┘

叠加：AgentPhoneModal、WorldEventModal、PhaseToast、LoadingOverlay
```

**删除**：`ObserverPanel`、`useEnvStatus` 独立 tick 栏（tick 改显示在 StatusPanel 或 WorldEvent）。

### 6.2 四房间 grid 映射

**文件**：`web/src/utils/places.ts` 扩展

```typescript
export const ROOM_GRID: PlaceId[] = [
  "nvidia_reception",      // row0 col0
  "jensen_private_room",   // row0 col1
  "negotiation_room",      // row1 col0
  "openai_hq",             // row1 col1
];
```

### 6.3 新组件

```
web/src/features/world-stage/
├── WorldStage.tsx
├── RoomGrid.tsx
├── RoomCell.tsx
├── AgentCircle.tsx
├── RoomSpeechBubble.tsx
├── AgentPhoneModal.tsx
├── MessageThreadList.tsx
├── InnerOsTimeline.tsx
└── WorldEventModal.tsx
```

| 组件 | 职责 |
|------|------|
| `RoomGrid` | CSS Grid 2×2，渲染四个 `RoomCell` |
| `RoomCell` | 房间标题 + `AgentLayer` + `BubbleLayer` |
| `AgentCircle` | 圆点 + 名字；click → 打开手机面板；**位置由 `agentLocations[id].placeId` 决定父 RoomCell** |
| `RoomSpeechBubble` | 房间内 F2F 短气泡，新消息淡入，保留最近 3 条或 5 秒淡出 |
| `AgentPhoneModal` | 私信 Tab / 群聊 Tab / `InnerOsTimeline` |
| `WorldEventModal` | 世界广播与路由事件居中弹窗 |

### 6.4 Agent 圆点随移动换格（核心交互）

**数据流**：

```text
Runner move → agent_location_log + agent_location 更新
  → Flask delta.location_changes + delta.agent_locations
  → gameStore APPLY_WORLD_DELTA
  → AgentCircle 重新挂载到目标 RoomCell
```

**前端实现要点**：

1. **权威状态**：`gameState.agentLocations: Record<agentId, { placeId, arrivedAt }>`。
2. **每 poll delta**：
   - 先用 `agent_locations` **全量覆盖**（防 drift）；
   - 对 `location_changes` 中每条变更，若 `from_place !== to_place`，触发 **移动动画**。
3. **渲染模型**：每个 `RoomCell` 渲染 `agents.filter(a => agentLocations[a].placeId === this.placeId)`；**不用**手动 DOM 搬节点，由 React key + CSS transition 实现视觉连续。
4. **动画**（`AgentCircle.tsx` + CSS）：
   - 方案 A（推荐）：圆点 `position: absolute` 在 `RoomGrid` 层，用 `transform: translate` 从旧格中心 **过渡 400ms** 到新格中心（需 grid 内各 cell 的 bounding rect）；
   - 方案 B（简单）：旧格 fade-out + 新格 fade-in 200ms。
5. **多 Agent 同室**：谈判室 5 人 — 圆点 **扇形/网格微偏移**，避免重叠；hover 显示全名。
6. **玩家圆点**：固定 agent 伪 ID `"player"`，位置 = `session.placeId`；Phase 路由后随 session 更新。

**验收**：节点 A（Jensen → 私人室）、节点 B（Jensen → 谈判室）、节点 C（CEO → 前台）时，圆点 **实时离开原格、进入新格**。

### 6.5 gameStore 重构

**移除**：`f2fMessages`, `rdcMessages`, `grpMessages` 独立数组（或保留仅作迁移兼容一层）。

**新增**：

```typescript
agentLocations: Record<number, { placeId: string; arrivedAt: number }>;
roomF2f: Record<PlaceId, GameMessage[]>;
agentInbox: Record<number, AgentInbox>;  // { rdcThreads, grpThreads, osLog, archivedThreadIds }
worldEvents: WorldEvent[];
pendingWorldEvent: WorldEvent | null;
activeAgentModal: number | null;
animatingMoves: LocationChange[];  // 可选，驱动 CSS 动画
```

**Actions**：

- `APPLY_WORLD_DELTA` — merge 消息、更新 locations、触发移动动画队列
- `OPEN_AGENT_MODAL` / `CLOSE_AGENT_MODAL`
- `DISMISS_WORLD_EVENT`
- `SET_WORLD_SNAPSHOT` — session refresh 校准

### 6.6 Thread 生命周期（群退 / 关系断）

```text
活跃 thread
  → social_event (group_leave | relation_remove)
  → 追加系统 GameMessage（is_system=true）
  → thread.status = "archived"
  → 不再 merge 该群/对该端 delivered=1 新消息
  → 历史保留
```

系统文案：

- 群退：**「您已退出该群聊」**
- 关系断：**「与对方关系已断裂」**

### 6.7 useGameLoop 改造

1. `postPlayerTurn` → 轮询 `action-result?since_tick=`（不变）
2. 每次 `delta` → `dispatch({ type: "APPLY_WORLD_DELTA", delta })`
3. `delta.world_events` 非空 → `SET_PENDING_WORLD_EVENT` → `WorldEventModal`
4. Turn completed → `refreshSession()` + 可选 `GET /world-snapshot`
5. 删除对 `ObserverPanel` 的数据依赖

### 6.8 删除/弃用

| 路径 | 动作 |
|------|------|
| `features/observer/ObserverPanel.tsx` | 删除或 stub |
| `features/layout/ThreeColumnLayout.tsx` | 改为两栏 `TwoColumnLayout` |
| `global.css` `.panel--observer` | 删除 |
| `gameStore` rdc/grp 独立 reducer 分支 | 移除 |

---

## 七、实施分期

### Phase 1 — Runner 持久化 + Schema（~1 天）

- [x] DDL + WorldDB insert/fetch
- [x] dispatcher / ipc_handlers / place_mutation 写 log
- [x] world_reset 清 log
- [x] 单元测试：move 与 update_state 后 DB 有行

### Phase 2 — Flask F12 API（~1–2 天）

- [ ] F06 扩展查询
- [ ] `f12_world_sync` 模块
- [ ] 扩展 F11 delta + F03 handler
- [ ] routing → world_events
- [ ] `test_f12_world_delta.py` + 更新 acceptance

### Phase 3 — 前端世界视图（~2–3 天）

- [ ] 两栏布局 + RoomGrid + AgentCircle + 移动动画
- [ ] RoomSpeechBubble
- [ ] gameStore + useGameLoop
- [ ] AgentPhoneModal + InnerOsTimeline
- [ ] WorldEventModal
- [ ] 删除 Observer

### Phase 4 — 联调与回归

- [ ] Turn1–4 手动走查（F2F 气泡、Jensen 移动、广播弹窗）
- [ ] `test_message_visibility_gap.py` 改为断言 F12 无 hidden
- [ ] `test_m0_acceptance` 全绿

---

## 八、测试与验收标准

| 场景 | 预期 |
|------|------|
| Turn1 前台 F2F | 接待室气泡；点 Agent1 手机可见 thread |
| Jensen RDC→VP | 谈判室无 F2F 气泡；Jensen/VP 手机有 RDC |
| 节点 A 路由 | Jensen 圆点 **从谈判室/前台侧移到私人室**；WorldEvent + PhaseToast |
| 节点 B 路由 | Jensen 圆点 **移到谈判室**；PlaceMutation 弹窗 |
| 节点 C 路由 | CEO 4/5/6 圆点 **移到前台** |
| Turn16 广播 | WorldEventModal；谈判室 Agent 手机有系统 RDC |
| update_state | Agent 手机 OS 时间线新增 |
| 群退 / 关系断 | thread 系统句 + 归档 + 无新消息 |
| 无右栏 | UI 两栏；信息可从 Agent 手机还原 |

---

## 九、风险与约束

1. **Runner 必须运行**：Flask 读 DB + 偶发 IPC 校准；无 Runner 则 locations 空、圆点不显示。
2. **移动动画性能**：四房间 + ≤7 Agent，transform 动画足够；避免每 tick 全量 relayout。
3. **F07 fallback 模板 F2F**：本方案先 **展示**；`GameMessage` 可加 `source: "scripted"` 供调试，后续 F07-F 去模板后再隐藏。
4. **玩家无 agent_id**：用 `"player"` 伪 ID + `placeId` 定位，不参与手机面板。

---

## 十、文件改动总表

| 层 | 新增/修改 |
|----|-----------|
| **Schema** | `agent_location_log.sql`, `agent_state_log.sql` |
| **Persistence** | `persistence/world_db.py` |
| **Runner** | `dispatcher.py`, `ipc_handlers.py`, `place_mutation.py`, `world_reset.py`, `ipc_helper.py` |
| **Flask F12** | `features/f12_world_sync/*`, `f06/world_db.py`, `f11/delta.py`, `f03/*`, `f05/routing.py`, `http/routes.py` |
| **前端** | `features/world-stage/*`, `TwoColumnLayout`, `gameStore.ts`, `useGameLoop.ts`, `api/types.ts`, `api/hbm.ts`, `places.ts`, `global.css` |
| **测试** | `scripts/test_f12_world_delta.py`, 更新 `test_m0_acceptance.py` |

---

## 十一、与 dev_logs/30 的关系

| 项目 | dev_logs/30 | 本方案 F12 |
|------|-------------|-----------|
| API 扩展 delta | PR4 F12 stub | **本方案完整实现** |
| Observer Tab | 扩展 background_f2f 等 | **取消右栏**，改四房间 + 手机面板 |
| Runner 改动 | 未强调 OS/location log | **§四 明确最小 Runner 改动** |
| Agent 移动 UI | 未描述 | **§五.4 / §六.4 圆点换格 + 动画** |

F07-F（去 fallback、Agent 原生输出）与本方案 **正交**：F12 可先落地全量展示；F07-F 改善内容质量。

---

**下一步**：在 `feature/f12-full-world-ui-sync` 按 Phase 1 → 2 → 3 → 4 实施；每 Phase 结束跑 acceptance 并 push。
