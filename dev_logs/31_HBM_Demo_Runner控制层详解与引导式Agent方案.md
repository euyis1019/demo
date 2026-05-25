# 开发日志 31：HBM Demo Runner 控制层详解与引导式 Agent 方案

**记录时间**：2026-05-24  
**状态**：分析文档（设计参考，与实施待办见 dev_logs/30）  
**前置文档**：

- [`dev_logs/30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md`](30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md) — 修复实施总方案（PR1–PR4）
- [`dev_logs/24_HBM_Demo_Agent行为控制整合方案.md`](24_HBM_Demo_Agent行为控制整合方案.md) — F07 ABCS（L2–L6）原设计
- [`dev_logs/29_HBM_Demo_F07_体验补强方案.md`](29_HBM_Demo_F07_体验补强方案.md) — F07-E 体验补强（E0–E6）

**关联代码**：`agent_world/hbm_demo/core/runner/`、`features/f07_agent_control/`

---

## 一、文档目的

玩家在本地实测与代码审计后，对「问题到底出在哪一层」存在困惑：

- 是 **Agent 本身说话/行为太少**？
- 还是 **Agent 其实做了很多事，被 Flask 应用层拒绝/过滤**？

本文 **完整记录** 对该问题的结论，并 **系统说明 Runner 控制层（F07）控制哪些内容**，以及 **如何用引导而非硬规则** 让 Agent 产出期望行为。

**核心结论（先读）**：

1. **主因在 Runner 控制层 + F07-E 硬补丁**，不是 Flask 拒绝 Agent 行为。
2. 当前实测 run 中，world.db 消息很少；Flask **几乎未隐藏** 已有消息。
3. 应回归 dev_logs/24 的 **ABCS 软引导**，弱化或移除 F07-E 的 **do_nothing 守卫、scripted fallback、E3 notify**。

---

## 二、问题定位：Agent 太少 vs Flask 拒绝？

### 2.1 三层架构

```text
┌─────────────────────────────────────────────────────────┐
│ Flask（编排层）                                          │
│  • 组装 inject / turn_context                           │
│  • 读 world.db → action-result / delta                  │
│  • 决定「哪些 channel、哪些 place」展示在哪个 UI 栏       │
│  • 【不】阻止 Runner 内 Agent dispatch                    │
├─────────────────────────────────────────────────────────┤
│ Runner 控制层（F07 + HbmWorldStep + HbmAgent）            │
│  • 每 Turn inject 批：N tick（常见 12）                  │
│  • 谁 tick、用什么工具、看什么 prompt、温度/长度         │
│  • tool_guard / fallback / notify → 写 world.db         │
├─────────────────────────────────────────────────────────┤
│ 引擎（agent_world 核心）                                 │
│  • LLM 调用、ActionDispatcher、FaceToFaceBus、RDC 落库   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 实测 world.db 摘要（2026-05-24 玩家 run）

环境：`current_tick=24`（约 2 Turn × 每 Turn 12 tick inject）

| 类型 | 条数 | 说明 |
|------|------|------|
| F2F @ `nvidia_reception` | 2 | **与 `f2f_fallback.py` 模板逐字一致**，非 LLM 自然输出 |
| RDC @ `negotiation_room` | 5 | 全部 **Jensen(2)→Tech VP(3)**，LLM 生成但内容重复 |
| Agent1→Jensen RDC | 0 | 剧情链「前台通报」缺失 |
| CEO F2F / GRP | 0 | 本次被动 tick 未产出可见消息 |

审计脚本：`agent_world/hbm_demo/scripts/test_message_visibility_gap.py`

**Turn1（tick 0–12）**：world 5 条 → API 可见 5 条，`hidden_count=0`  
**Turn2（tick 12–24）**：world 2 条 → API 可见 2 条，`hidden_count=0`

### 2.3 二选一结论

| 说法 | 是否成立 |
|------|----------|
| Agent 说话/行为本身就太少？ | **是，主因**（尤其前台；CEO 本次为 0） |
| Agent 做了很多，被 Flask 拒绝？ | **本次 run：否**（7 条全展示） |
| 结构性 UI 缺口？ | **潜在是**（非玩家地点 F2F、update_state 等当前 API 不返回，见 dev_logs/30 §5） |

**更精确表述**：

- 问题在 **Runner + F07-E 硬规则**（守卫 → 空 tick → 模板兜底；E3 → Jensen 越权），使 Agent **要么说不出话，要么链式剧情错误**。
- Flask **按契约筛选展示**，未在本次测试中「挡掉大量已有行为」。
- **24 tick ≠ 24 句台词**；tick 是引擎调度次数，多数 tick 未写入 `direct_message`。

---

## 三、一次 Turn 的因果链（现象解释）

```text
玩家: 「我要见黄仁勋，KV Cache 降 80%…」
        │
        ▼
Flask: build_turn_context + inject 前缀(L4+L6) → Agent1 player_memory
        │
        ▼
Runner tick 0 (inject_exclusive: 仅 Agent1)
        │
        ├─ HbmAgent: 看到 L6 + 知识库 + 玩家句
        ├─ LLM 输出: send_message → Jensen   （常见习惯）
        ├─ tool_guard E1: 尚未 F2F → 整批改成 do_nothing  （硬限制）
        └─ world.db: 无新消息
        │
        ... tick 1~11 类似 ...
        │
        ▼
批末 fallback: 写模板 F2F「您提到的80%…请稍等」  （硬替 Agent 说话）
        │
        ▼
E3 notify 已把玩家全文给 Jensen → Jensen 多次 RDC→VP  （LLM 有输出但链错）
        │
        ▼
Flask 读库 → 中屏 1 条模板 + Observer 多条 Jensen RDC
        │
        ▼
用户感受: 「tick 24 但只有前台+黄仁勋重复」——与数据一致
```

---

## 四、Runner 控制层控制项总览

HBM Demo 在引擎外包一层 **`HbmWorldStep` + `HbmAgent` + F07 配置**。每个玩家 Turn 对应一次 **IPC inject 批**（experience_hardening 下 Phase1/2/4 常为 **12 tick**）。

对照 dev_logs/24 的 **L2–L6** 与 F07-E 补丁：

| 层级/模块 | 主要文件 | 控制什么 | 硬/软 |
|-----------|----------|----------|-------|
| **批编排** | `core/runner/ipc_handlers.py` | tick 次数、批末 fallback | **硬** |
| **L3 谁动** | `pick_active.py`, `turn_control.yaml` | 本 tick 哪些 Agent 调 LLM | 半硬（剧情结构） |
| **L5 工具** | `tool_matrix.yaml`, `tool_guard.py` | 工具白名单；非法→do_nothing | **硬** |
| **L6 怎么说** | `player_response.py` | inject 约束、玩家句、Phase 规则 | **软（引导）** |
| **L4 知道什么** | `knowledge.py`, `story_knowledge/` | 世界态、角色目标、Turn hints | **软（引导）** |
| **L2 说多少** | `llm_params.py`, `turn_control.yaml` | temperature、max_tokens | **软（引导）** |
| **E0 F2F 通道** | `player_facing_f2f.py`, `world_step.py` | 玩家地点 F2F 落库 hook | 基础设施 |
| **E1 首动守卫** | `tool_guard.py` | 必须先 F2F，否则 do_nothing | **硬** |
| **E2 RDC 配额** | `tool_guard.py`, `batch_guard.py` | 超额 RDC→do_nothing | **硬** |
| **E3 Jensen 摘要** | `inject_batch.py` | Phase1 玩家全文 notify→Agent2 | **硬越权** |
| **E1 fallback** | `f2f_fallback.py` | 批末模板 F2F | **硬替 Agent 说话** |
| **Agent 运行时** | `hbm_agent.py` | observation 尾部的短行动规则 | 软+硬混合 |
| **批状态** | `batch_guard.py` | 本批 F2F/RDC 计数 | 中性（用法决定软硬） |
| **inject 上下文** | `turn_context.py` | turn_context IPC 载荷 | 编排 |
| **记忆** | `turn_context.clear_player_memory_for_agents` | inject 前清 player_memory | 半硬 |

---

## 五、分项详解

### 5.1 批编排（`ipc_handlers` + `HbmWorldStep`）

**控制内容**：

- `resolve_inject_tick_loops(tick_count)`：experience_hardening 下 cap=12。
- 每 tick 调用 `world_step.run_one_tick()`，`_batch_tick_index` 递增。
- 批 `finally`：若启用 E1，调用 `apply_batch_f2f_fallback_at(end_tick)`。

**关键代码路径**：

- `agent_world/hbm_demo/core/runner/ipc_handlers.py` — inject 循环与 fallback
- `agent_world/hbm_demo/core/runner/world_step.py` — `set_tick_context` / `clear_tick_context`

**问题关联**：tick 多但对话少，因多数 tick 未落库；批末 fallback 产生「死板中屏句」。

---

### 5.2 L3 — 谁在这一 tick 运行 LLM（`pick_active`）

**配置来源**：`turn_control.yaml` → `phases.Phase N`

| 概念 | 含义 | Phase1 示例 |
|------|------|-------------|
| `primary_active` | 本 Phase 主舞台 Agent | `[1, 2, 3]` |
| `frozen` | 本 Phase 不 tick | `[7]` Sam |
| `present_silent` | 在室但不 tick | Phase4 VP `[3]` |
| `inject_exclusive_ticks` | 批内前 N tick 仅 inject 目标 | Phase1: `2` |
| `passive_low_freq` | 低频被动（CEO 等） | `[4, 5, 6]` |
| `passive_max_per_batch` | 每批最多被动 tick 数 | `1` |
| `passive_tick_probability` | 被动触发概率 | low/medium/high |

**逻辑**（`pick_active_ids`）：

1. 若 `batch_tick_index < inject_exclusive_ticks` → 只返回 inject 目标（如 Phase1 仅 Agent1）。
2. 否则合并 `primary_active`（去 frozen）。
3. 再按概率加入 passive 候选（有未读 RDC/F2F 等条件）。

**性质**：**剧情舞台控制**，合理保留。问题不在「谁可以动」，而在动起来后被 L5/E1 拦死。

---

### 5.3 L5 — 工具白名单与守卫（`tool_matrix` + `tool_guard`）

**矩阵示例**（Phase1 前台 Agent1）：

```yaml
1: [speak_to_local, send_message, do_nothing, update_state]
move_allowed: false  # 全员 Phase1 禁止 request_move
```

**`filter_tool_calls` 处理顺序**（experience_hardening）：

```text
first_action_guard (E1)
  → rdc_quota (E2)
  → is_tool_allowed (矩阵)
```

**E1 首动 F2F 守卫**（`first_f2f_required`）：

- Phase1：`[1]` 前台必须先 F2F。
- 若 `batch_guard.has_f2f(agent)` 为 false，仅允许 `speak_to_local` / `do_nothing`。
- 若 LLM 输出 `send_message` 等 → **整批 tool_calls 替换为单个 `do_nothing`**。

**这是体验问题的主因之一**：

- LLM 常先 RDC 再 F2F（与 prompt 相反）。
- 守卫不「纠正次序」，而 **废掉整 tick** → 多次空 tick → 批末 fallback。

**E2 RDC 配额**（`rdc_quota_per_batch`）：

- Phase1：Agent1→1 条，Agent2→2 条，Agent3→1 条（配置值）。
- 超额 → 同样 **整批 do_nothing**。
- 并行 tick 下 `BatchGuardState` 可能存在竞态，导致配额失效（实测 Jensen 单 Turn 4 条 RDC）。

---

### 5.4 L6 + L4 — Prompt 与知识库（软引导层）

**inject 路径**（仅 inject 目标，如 Phase1 Agent1）：

`format_inject_dialogue` → `build_agent_knowledge(channel="inject")` 组装：

1. **L6** `format_l6_player_directive` — 系统约束、玩家 verbatim、Phase 规则
2. **共享 Phase Bible** — `story_knowledge/shared/phase_N.yaml`（世界态、剧情要点、禁止项）
3. **Agent overlay** — `story_knowledge/agents/agent_N.yaml`（口吻、关系、phase_overrides、范例、checklist）
4. **Turn hints** — `turn_hints.yaml`

**notification 路径**（非 inject 的 primary Agent，如 Phase1 Jensen/VP）：

- `build_notification_snippet` — 较短摘要
- **默认看不到玩家原话**（设计如此，逼 RDC 链）
- **E3 破坏此设计**：`notify_jensen_player_summary` 把玩家全文 notify 给 Agent2

**性质**：dev_logs/24 推荐的 **主要引导手段**。当前不足：与 E1/E3/fallback 冲突，导致引导失效。

---

### 5.5 L2 — 温度与长度（`llm_params`）

**Phase 表示例**（`turn_control.yaml`）：

| Key | temperature | max_tokens | 用途 |
|-----|-------------|------------|------|
| Phase 1 | 0.45 | 180 | inject 主活跃（前台等） |
| Phase_1_passive | 0.35 | 120 | Phase1 Jensen/VP 被动 tick |
| Phase 2 | 0.50 | 220 | 私密审查 |
| Phase 3 | 0.62 | 350 | 舌战（可略长） |
| Phase 3_turn16 | 0.68 | 400 | Turn16 高潮 |
| Phase 4 | 0.48 | 200 | 终局 1v1 |

**应用点**：`HbmWorldStep._resolve_batch_llm_params` — Phase1 被动 Agent 2/3 使用 `Phase_1_passive`。

**性质**：纯软引导，控制口语化与篇幅。

---

### 5.6 E0 — 玩家 F2F 通道（`player_facing_f2f`）

**背景**：玩家不是引擎 Agent；前台 alone @ reception 时 `speak_to_local` 的 FaceToFaceBus 可能 0 recipient。

**机制**：

- dispatch 成功后，若 `should_emit_player_facing_f2f` → `emit_player_facing_f2f(recipient_id=0)`。
- Flask `fetch_f2f_history_at(task.place_id)` → 中屏 `public_messages`。

**性质**：必要基础设施，**不是限制**。

---

### 5.7 E3 — Jensen 玩家摘要 notify

**代码**：`inject_batch.notify_jensen_player_summary`

**行为**：Phase1 每 Turn 将玩家原话 script notify 给 Agent2。

**后果**：

- Jensen **无需** 前台 RDC 即知玩家内容。
- Observer 出现大量 Jensen→VP「前台有人说…」式 RDC，**跳过前台→Jensen 链**。
- 与 dev_logs/24 Phase1 叙事及用户期望 **直接冲突**。

**建议**：Phase1 **关闭**（见 dev_logs/30 PR1）。

---

### 5.8 E1 Scripted Fallback（`f2f_fallback.py`）

**模板**：

| Phase | 模板 |
|-------|------|
| Phase 1 | 「您提到的{kw}，我需要跟黄总确认，请稍等。」 |
| Phase 2 | 「{kw}——外面的人在等，你继续。」 |
| Phase 4 | 「{kw}，我们可以再谈条件。」 |

**关键词**：`extract_player_keyword` — 先匹配 `\d+%`，再 `_KEYWORD_HINTS`，否则截前 20 字。

**触发**：批末 `batch_guard.has_f2f(required_agent)` 仍为 false → 写库。

**性质**：**100% 硬编码替 Agent 说话**；用户实测中屏 2 条 F2F 均为此路径。

**建议**：默认关闭；completion 改为等待 LLM F2F（见 dev_logs/30）。

---

### 5.9 `HbmAgent` 运行时规则

**机制**：`_observation_to_text` 在有 `player_memory` 时跳过 stale 强制 update_state；`_replace_demo_tail` 注入 `_hbm_short_action_rules()`。

**规则要点**：

- 必须先回应玩家 inject 记忆
- 1–4 句口语（Phase3/4 略变）
- 角色/Phase 专属 bullet（前台：先 F2F 再 RDC→Jensen）
- 每拍一个工具

**与 L6 关系**：内容重叠，属于 **文本引导**；但若 tool_guard 整批 do_nothing，规则无法落地。

---

### 5.10 `BatchGuardState`

**字段**：

- `f2f_sent: Set[agent_id]`
- `rdc_sent: Dict[agent_id, count]`

**用途**：

- E1：是否已 F2F → 能否发 RDC
- E2：RDC 计数 → 配额
- completion：是否有 player-visible F2F
- fallback：是否需模板

**性质**：状态容器；**应用方式**决定体验好坏。

---

### 5.11 Flask 读库与展示（非 Runner，但影响「看到什么」）

**`get_action_result` / `build_turn_delta`**：

| API 字段 | 数据来源 | UI |
|----------|----------|-----|
| `public_messages` | `fetch_f2f_history_at(task.place_id)` | 中屏 |
| `observer_messages` | 全局 `channel_type=RDC` | Observer Tab RDC |
| `group_messages` | 全局 `channel_type=GRP` | Observer Tab GRP |

**不返回**：

- 非 `task.place_id` 的 F2F（如谈判室 CEO 短句）
- `update_state` / 内心 OS
- MOVE / Phase 切换事件流（仅 session toast）

详见 dev_logs/30 §5（F12 全量同步方案）。

---

## 六、硬限制 vs 软引导：适用边界

| 手段 | 适合 | 不适合 |
|------|------|--------|
| 知识库 + L6 + 范例 + checklist | 角色口吻、Phase 目标、行为顺序建议 | 单独使用无法 100% 保证合规 |
| temperature / max_tokens | 长短、口语化 | 不能保证剧情链 |
| L3 primary/frozen/passive | Phase 舞台（谁在场、谁冻结） | 不能替代台词内容 |
| 工具矩阵禁止 MOVE/GRP | 防止 Agent 破坏 Flask 路由的结构动作 | 不宜用来「必须先 speak_to_local」 |
| filter → **do_nothing** | **几乎不应作为引导** | 造成空 tick + fallback |
| **scripted fallback** | 仅紧急 CI（可选） | **真实玩家体验** |
| **notify 玩家全文给 Jensen** | 无 | 破坏前台链 |
| **Stats gate 路由** | 无（用户期望 Agent 驱动） | Phase 切换 |

---

## 七、引导式 Agent 方案（非硬规则）

目标：**Agent 在正确上下文下自己生成正确行为**；编排层只做 **舞台、边界、后果反馈、轻量纠错**。

### 7.1 总体哲学

```text
┌─────────────────────────────────────────┐
│ 软引导（主）                             │
│  知识库 · L6 · turn_hints · 范例 · L2   │
│  → Agent 自己生成台词与顺序              │
├─────────────────────────────────────────┤
│ 结构边界（保留）                         │
│  L3 谁活跃 · 禁止 Agent 自行 MOVE/GRP   │
│  → 保证 Phase 舞台，不替 Agent 写词      │
├─────────────────────────────────────────┤
│ 后果反馈（替代 Stats gate）              │
│  扫 world.db 行为链 → 路由 Phase         │
│  → 「做对了世界会变」（dev_logs/30）     │
├─────────────────────────────────────────┤
│ 轻量纠错（替代 do_nothing / fallback）   │
│  工具次序错了 → 改写成合法工具           │
│  → 不空转、不写模板                      │
└─────────────────────────────────────────┘
```

### 7.2 加强 L4 + L6（成本最低，优先）

**前台 Agent1 inject 知识库应明确两步剧本**（自然语言，非代码 if-else）：

1. **第一步** `speak_to_local`：1–2 句口语，含玩家关键词。  
2. **第二步**（若判断有价值）：**一条** `send_message→2`：「有人带了…可能很重要」——不展开技术。

**玩梗 Turn checklist**：

- 仅 F2F 礼貌接梗；**本 Turn 禁止** RDC→Jensen。

**Jensen/VP notification**：

- 「仅当前台 RDC 到达后再行动；本拍无新 RDC 则 do_nothing。」

**turn_hints**：

- 写「本 Turn 目标：完成通报链 / 私密审查 / …」，**不写** Stats 门槛文案。

### 7.3 工具层：改写而非 do_nothing（dev_logs/30 PR1）

```text
❌ 现状:
   LLM 先 send_message → E1 → 整批 do_nothing → 空 tick

✅ 建议:
   LLM 先 send_message 且尚未 F2F
   → 改写为 speak_to_local(content=从 player_memory/args 提炼的 1–2 句)
   → 同 tick 或下一 tick 再允许 RDC（batch_guard 已 mark_f2f 后）
```

**区别**：

- **fallback**：固定模板，非 LLM。  
- **改写**：内容仍来自 LLM 上下文，只是 **工具类型** 被编排层纠正。

### 7.4 L3 tick 序：给机会，而非禁令

- tick 0–2（或 0–3）：**仅 Agent1** — 集中完成 F2F + 首条 RDC→2。  
- tick 3+：Jensen/VP 响应前台 RDC。  
- tick 6+：CEO 低频被动。

这是 **scheduling 引导**，不是把 LLM 输出改成 do_nothing。

### 7.5 L2 调参建议

| 角色/场景 | 建议 |
|-----------|------|
| 前台 F2F | temperature 0.5–0.6，max_tokens 120–150 |
| Jensen/VP 被动 RDC | temperature 0.35–0.45，max_tokens 80–120，prompt 强调「每条≤2句」 |
| Phase3 舌战 | 维持较高 temperature + max_tokens |

### 7.6 世界后果引导（替代 Stats）

**路由**（dev_logs/30 agent_signals）：

- Phase1→2：检测 **1→2 + 2→3 + 2→1 approve** RDC 链 → MOVE，**不看** V+E。  
- Agent 做对 → session phase/place 变；做错 → 停留 Phase1，下 Turn 自然压力。

**Bad End**：

- 前台 F2F 明确拒绝，或长期无 approve 信号 — **非** Turn4 Stats stub。

### 7.7 可选：`story_advance` 信号工具

```python
story_advance(signal: Literal[
  "approve_visitor", "reject_visitor",
  "return_to_negotiation", "expel_ceos",
  "offer_join", "offer_seed",
])
```

- **台词**仍由 speak_to_local / send_message 自由生成。  
- **路由**只读信号落库，减少 NL 误判。  
- 比 fallback 透明，比 Stats 符合「Agent 决策」。

### 7.8 应删除或默认关闭的项

| 项 | 建议 |
|----|------|
| `scripted_f2f_fallback` | **false**，移除批末调用 |
| `notify_jensen_player_summary`（Phase1） | **关闭** |
| E1 → do_nothing | 改为 **speak_to_local 改写** |
| Turn4 Stats Bad End | **Agent 驱动拒绝** |
| completion 依赖 fallback F2F | **LLM F2F + 有限补呼** |

---

## 八、Phase1 期望对话链（引导目标）

对齐 dev_logs/24 与用户期望：

```text
玩家
  ↓ F2F
前台 Agent1 — 短句回应玩家（含关键词）
  ↓ RDC 1→2（一条简报，非技术细节）
Jensen Agent2 — 与 VP 讨论
  ↓ RDC 2→3
Tech VP Agent3 — 技术评估 RDC 3→2
  ↓ RDC 2→1（approve：私密会议室 / 可以见）
前台 Agent1 — F2F 玩家「请跟我来」
  ↓
Flask 路由节点 A — MOVE Jensen + 玩家 place → Phase2
```

**不应出现**：

- 批末模板 F2F  
- E3 全文 notify 使 Jensen 跳过 1→2  
- Stats Turn4 硬性 gate（若采用 agent_driven 路由）

---

## 九、与 dev_logs/30 的衔接

| 本文章节 | dev_logs/30 实施项 |
|----------|-------------------|
| §5.7 E3、§5.8 fallback、§7.3 守卫改写 | **PR1** 去硬编码 |
| §5.3 E2、§7.4 tick 序 | **PR2** RDC 链 + quota 锁 |
| §7.6 世界后果 | **PR3** agent_signals 路由 |
| §5.11 Flask 缺口 | **PR4 F12** 全量 delta + Observer Tab |

本文 **偏分析与设计原则**；**代码改动清单与验收** 以 dev_logs/30 为准。

---

## 十、代码索引

| Topic | Path |
|-------|------|
| IPC inject 批 | `core/runner/ipc_handlers.py` |
| World step / F2F hook | `core/runner/world_step.py` |
| HbmAgent 规则 | `core/runner/hbm_agent.py` |
| pick_active | `features/f07_agent_control/pick_active.py` |
| tool_guard | `features/f07_agent_control/tool_guard.py` |
| tool_matrix | `features/f07_agent_control/tool_matrix.yaml` |
| turn_control | `features/f07_agent_control/turn_control.yaml` |
| knowledge / L6 | `features/f07_agent_control/knowledge.py`, `player_response.py` |
| fallback | `features/f07_agent_control/f2f_fallback.py` |
| Jensen notify | `features/f07_agent_control/inject_batch.py` |
| turn_context | `features/f07_agent_control/turn_context.py` |
| action-result | `features/f03_action_result/handler.py` |
| delta | `features/f11_live_turn_sync/delta.py` |
| 可见性审计 | `scripts/test_message_visibility_gap.py` |

---

## 十一、FAQ

**Q：增加 tick 数能否让 Agent 说更多话？**  
A：不能根治。若每 tick 被 do_nothing 或重复 RDC，加 tick 只增加空转与重复。应先修 guard + fallback，再酌减 tick（如 12→8）。

**Q：只改 prompt 不改 guard 够不够？**  
A：不够。实测 LLM 仍常先 RDC；E1 会 do_nothing。需 **prompt + 工具改写 + 关 fallback** 组合。

**Q：Flask 要不要改？**  
A：Runner 修好后中屏会有真 LLM F2F。若要看 CEO 背景 F2F、内心 OS，还需 dev_logs/30 F12 扩展 API/UI。

**Q：L3 frozen / 禁止 MOVE 算不算硬规则？**  
A：算 **结构边界**，与「替 Agent 写台词」不同；建议保留。

---

**文档版本**：v1.0 · 2026-05-24  
**下一步**：实施见 [`dev_logs/30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md`](30_HBM_Demo_F07-F_Agent原生输出与全量同步方案.md) PR1 起。
