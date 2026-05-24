# 开发日志 29：HBM Demo F07 体验补强方案（F07-E）

**记录时间**：2026-05-23  
**分支**：`feature/f07-agent-behavior-control`（或自其拉 `feature/f07-e-experience-hardening`）  
**状态**：方案定稿 · 待实施  
**Feature ID**：**F07-E — ABCS 体验补强（Experience Hardening）**  
**前置**：**F07-A/B/C/D 已落地** @ `ce8d74d`；**F11** 已合并  

**关联文档**：
- ABCS 主方案（已实施）→ [`24_HBM_Demo_Agent行为控制整合方案.md`](./24_HBM_Demo_Agent行为控制整合方案.md)
- F07-D 后体验评测结论 → 本会话测试报告（2026-05-23）
- 剧情原型 → [`dev_docs/1_story_prototype.md`](../dev_docs/1_story_prototype.md)
- F11 增量同步 → [`28_HBM_Demo_F11_回合内增量同步方案.md`](./28_HBM_Demo_F11_回合内增量同步方案.md)

---

## 0. 摘要

F07 ABCS **架构层**（L2–L6、F03 Phase 1/4 专规、inject/L3/L5）已按 dev_log/24 落地并通过 `test_m0_acceptance` 全量回归。  
**F07-D 后 LLM 实测**表明：Observer 侧 RDC 链能引用玩家关键词，但 **中屏 F2F 经常为 0**、前台 **同 Turn 重复 RDC**、**玩梗输入未被识别** 等问题仍使玩家「感受不到交互」。

本方案将上述缺口整理为 **6 项可实施优化**，打包为 **F07-E**（Experience Hardening），在 **不改引擎核心**、**不破坏 F05 路由 / F11 异步** 前提下，用 **Runner 编排层硬约束 + Prompt 补强 + 测试收紧** 解决。

| 优先级 | 问题 | 方案代号 |
|--------|------|----------|
| **P0** | Phase 1/2 **引擎层**无 F2F 落库（玩家非 Agent） | **E0** 玩家可见 F2F 通道（v1.1 新增） |
| **P0** | Phase 1/2/4 中屏 F2F 缺失 | **E1** 首动 F2F 守卫（依赖 E0） |
| **P0** | 前台同批重复 RDC 刷屏 | **E2** 批内动作去重 / tick 序 |
| **P1** | Turn 2+ 玩梗/闲聊未回应 | **E3** 本 Turn 玩家句优先 |
| **P1** | 非 inject Agent 跑题（幻觉） | **E4** 被动 tick 上下文收窄 |
| **P1** | 无 F2F 仍 completed | **E5** F03 + Tier B 硬断言 |
| **P2** | session/start 污染 / Phase 4 无 E2E | **E6** 会话卫生 + 终局冒烟 |

---

## 1. F07-D 后问题清单（评测依据）

### 1.1 自动化测试 vs 真实体验

| 检查项 | 自动化结果 | LLM 实测（有 Key） |
|--------|------------|-------------------|
| M0–M7 全量 | ✅ PASS | — |
| Phase 1 GRP=0 | ✅ | ✅ |
| Phase 1 无 MOVE | ✅ | ✅ |
| Tier B `F2F≥1 OR observer≥1` | ✅（observer=2~3） | **F2F=0** 仍通过 |
| inject 前缀 / L3 / L5 | ✅ 单元 | — |
| 玩家关键词进 RDC | 未断言 | ✅（80%、KV、kernel 等） |
| 玩梗 Turn 2 回应 | 未覆盖 | ❌ 仍沿 Turn 1 技术线 |
| 前台 RDC 条数 | 未限制 | ❌ 单 Turn 6–8 条同类 RDC |

### 1.2 根因归纳

```
玩家输入 ──inject──► Agent 1 player_memory（仅 inject 目标）
                         │
         L6/Prompt 要求 speak_to_local 优先 ──► LLM 常忽略，直接 RDC
                         │
Phase 1 primary [1,2,3] 每 tick 并行 LLM ──► Agent 1 每 tick 再 RDC 一次
                         │
Jensen(2) 无 player_memory ──► 仅见 notification + 旧 RDC，不见 Turn 2 原话
                         │
F03 Phase 1：无 F2F 时 tick≥8 仍 completed ──► 中屏空但回合结束
```

**结论**：F07 的 **软约束（L6/Prompt）** 不足以保证玩家可感知交互；需要 **F07-E 硬约束层** 补齐。

---

## 2. 设计原则（F07-E）

1. **玩家中屏优先**：Phase 1/2/4 每 Turn **必须**有 ≥1 条与玩家本 Turn 输入相关的 F2F，否则回合不完成或引擎代发短 F2F。
2. **硬约束优于 Prompt**：LLM 不可靠时，由 L5 首动守卫 / 批内去重 / 代发兜底保证下限。
3. **本 Turn Scoped**：inject 目标以 **当前 Turn 玩家句** 为最高优先级；非 inject Agent 不得引用未注入的原话。
4. **可回滚**：`turn_control.yaml` 增 `experience_hardening:` 块，`enabled: false` 回退至纯 F07-D。
5. **不改引擎**：全部落在 `features/f07_agent_control/`、`core/runner/hbm_agent.py`、`f03`、`f01`、`scripts/test_*`。

---

## 3. 优化项详细方案

### E1 — 首动 F2F 守卫（P0）

#### 3.1.1 问题

- dev_log/24 §13.1：Phase 1 前台须 **先 `speak_to_local` 再 RDC**。
- 实测：Agent 1 多轮只 `send_message→2`，中屏 **F2F=0**。
- Phase 2 Jensen、Phase 4 Jensen 同理。

#### 3.1.2 方案：**L5.1 `first_action_guard`**（推荐主路径）

在 `tool_guard.py` 新增批内状态（挂 `turn_context` 或 `HbmWorldStep`）：

```yaml
# turn_control.yaml 增补
experience_hardening:
  enabled: true
  first_f2f_required:
    Phase 1: [1]          # inject 目标前台
    Phase 2: [2]
    Phase 4: [2]
```

**规则**（每个 inject 批内，对上述 agent）：

| 批内状态 | 允许的工具 |
|----------|------------|
| 该 Agent **尚未**发出本批首条 F2F | **仅** `speak_to_local`、`do_nothing` |
| 已发出 ≥1 条 F2F | 恢复 `tool_matrix.yaml` 白名单 |

实现要点：

```python
# tool_guard.py — 伪代码
def filter_tool_calls(agent_id, turn_context, tool_calls, *, batch_f2f_sent: set[int]):
    if not experience_hardening_enabled():
        return existing_filter(...)
    required = first_f2f_agents(turn_context)
    if agent_id in required and agent_id not in batch_f2f_sent:
        allowed = {"speak_to_local", "do_nothing"}
        # 非法工具 → do_nothing（与现有 L5 一致）
```

**状态跟踪**：在 `HbmWorldStep` 或 `ipc_handlers` inject 循环中：

- 批开始时 `batch_f2f_sent = set()`
- 每次 `dispatch` 成功 `speak_to_local` 后，将 `agent_id` 加入集合
- 传入 `filter_tool_calls`

#### 3.1.3 兜底：**Scripted F2F Stub**（LLM 仍不发 F2F 时）

若整批 tick 结束，`batch_f2f_sent` 仍不含 inject 目标，Runner **代写 1 条短 F2F**（不经过 LLM）：

| Phase | Agent | 兜底台词模板（含玩家关键词占位） |
|-------|-------|----------------------------------|
| 1 | 1 | 「您提到的{关键词}，我需要跟黄总确认，请稍等。」 |
| 2 | 2 | 「{关键词}——外面的人在等，你继续。」 |
| 4 | 2 | 「{关键词}，我们可以再谈条件。」 |

- 关键词：从 `turn_context.player_text` 抽取（数字、技术词、或前 20 字）。
- 写入 `direct_message` 渠道 F2F，`attempted_at = end_tick`。
- 文件：`features/f07_agent_control/f2f_fallback.py`（新模块，≤80 行）。

**开关**：`experience_hardening.scripted_f2f_fallback: true`（默认 true）。

#### 3.1.4 代码影响

| 文件 | 改动 |
|------|------|
| `turn_control.yaml` | `experience_hardening` 块 |
| `tool_guard.py` | `first_action_guard` + `batch_f2f_sent` 参数 |
| `world_step.py` / `ipc_handlers.py` | 批内 F2F 状态跟踪；批末 fallback |
| `f2f_fallback.py` | 新建 |
| `hbm_agent.py` | 无必须改动（守卫在 filter 层） |

#### 3.1.5 验收

- Phase 1 Turn 1：`public_messages` **≥1**，且 content 含玩家词（80%/显存/算法 任一）或兜底模板。
- Phase 2 / Phase 4 直接 inject 冒烟：Jensen F2F ≥1。
- `enabled: false` 时行为与 F07-D 一致。

---

### E2 — 批内 RDC 去重与 tick 序（P0）

#### 3.2.1 问题

Phase 1 `primary_active: [1,2,3]`，8 tick 内 Agent 1 **每 tick 可 LLM**，实测 **6–8 条** 几乎相同的「前台→Jensen」RDC，Observer 噪音大。

#### 3.2.2 方案 A：**L5.2 批内 RDC 配额**（推荐）

```yaml
experience_hardening:
  rdc_quota_per_batch:
    default: 1                    # 每 Agent 每批最多 1 条 RDC
    Phase 1:
      1: 1                        # 前台→Jensen 最多 1 条
      2: 2                        # Jensen→3 + 其他
      3: 1
```

在 `filter_tool_calls` 或 dispatch 前：

- 维护 `batch_rdc_count: Dict[(agent_id, recipient_id), int]`
- 超额 `send_message` → `do_nothing` + log

#### 3.2.3 方案 B：**Phase 1 首 tick 序**（与 E1 协同）

Phase 1 批内 tick 调度改为 **两阶段**（`pick_active.py` 或 `world_step`）：

```
Tick 1–2：仅 inject 目标 Agent 1（保证 F2F + 首条 RDC）
Tick 3+：primary [2,3] + passive CEO（原逻辑）
```

配置：

```yaml
experience_hardening:
  inject_exclusive_ticks:
    Phase 1: 2    # 前 2 tick 仅 inject 目标 tick
```

**推荐**：**A + B 同时实施**——序保证 F2F 优先，配额防止重复。

#### 3.2.4 代码影响

| 文件 | 改动 |
|------|------|
| `tool_guard.py` | RDC 配额计数 |
| `pick_active.py` 或 `world_step._pick_active` | `inject_exclusive_ticks` |
| `ipc_handlers.py` | 批内 quota 状态初始化/清理 |

#### 3.2.5 验收

- Phase 1 Turn 1：`observer_messages` 中 **前台→Jensen RDC ≤2**（允许 1 条主 RDC + 1 条被动修正）。
- Observer 总条数 ≤6（原 8+ 视为回归失败）。

---

### E3 — 本 Turn 玩家句优先（P1）

#### 3.3.1 问题

- Turn 2 玩家玩梗「送咖啡」，Agent 仍讨论 Turn 1 的「80% 显存」。
- 根因：Phase 1 仅 Agent 1 有 `player_memory`；Jensen 靠 notification/RDC，**若前台未报 Turn 2 内容则 Jensen 不可见**。

#### 3.3.2 方案

**（1）L6 补强 — `player_response.py`**

对 Agent 1 Phase 1 inject 通道追加：

```text
★ 本 Turn 唯一权威输入是下方「玩家说：…」——必须优先回应该句。
  禁止复读上一 Turn 或 notification 中的旧话题，除非玩家本句明确延续。
★ 若玩家明显闲聊/玩梗（无技术/见黄总诉求）：speak_to_local 礼貌回应即可，
  勿 send_message→Jensen；可说「您要是想谈技术方案，我可以帮您通报。」
```

**（2）前台 → Jensen 结构化 RDC 摘要**

inject 批开始时，除 `notify_non_inject_active_agents` 外，对 Agent 2 追加 **一条 scripted_notification**：

```text
【本 Turn 前台访客原话摘要】玩家说：「{player_text}」
请基于此句决定是否 RDC Tech VP；勿臆造未提及的情报（如三星 roadmap）。
```

实现：`inject_batch.py` → `notify_jensen_player_summary(turn_context, player_text)`。

**（3）A6 已 scoped 清空** — 确认每批 inject 前 `clear_player_memory_for_agents(inject_ids)` 仍执行（已实现，回归即可）。

#### 3.3.3 代码影响

| 文件 | 改动 |
|------|------|
| `player_response.py` | Turn-scoped / 闲聊分流 L6 |
| `inject_batch.py` | Jensen 本 Turn 摘要 notification |
| `story_knowledge/agents/agent_1.yaml` | `response_checklist` 增「闲聊不打扰 Jensen」 |

#### 3.3.4 验收

- 场景：Turn 1 技术句 → Turn 2 咖啡玩梗。
- Turn 2 中屏 F2F 含「咖啡/皮衣/等」之一 **或** 礼貌打发语。
- Turn 2 Observer：**不应**再出现新的「80% 显存」前台 RDC（闲聊分流成功）。

---

### E4 — 被动 tick 跑题抑制（P1）

#### 3.4.1 问题

Jensen Phase 1 被动 tick 出现与玩家无关的「三星 HBM roadmap」幻觉。

#### 3.4.2 方案

**（1）notification 收窄** — `build_notification_snippet` Phase 1 Agent 2/3：

```text
你只能依据「前台 RDC」与「本 Turn 摘要」行动；禁止编造未在 RDC/摘要中出现的公司名、数据、roadmap。
```

**（2）Phase 1 Agent 2/3 无 player_memory 时** — `hbm_agent._hbm_short_action_rules` 增：

```text
若本拍无新前台 RDC，选 do_nothing；勿主动发起与当前访客无关的话题。
```

**（3）可选降温** — `turn_control.yaml`：

```yaml
llm_params:
  Phase_1_passive: { temperature: 0.35, max_tokens: 120 }  # Agent 2/3 被动 tick
```

在 `world_step._run_single_agent` 对 passive tick（非 inject 目标）覆盖更低温度。

#### 3.4.3 验收

- Phase 1 Turn 1 Observer：Jensen RDC **不得**含「三星」「roadmap」等玩家未提词（人工 / 关键词黑名单断言）。

---

### E5 — F03 完成语义 + Tier B 测试收紧（P1）

#### 3.5.1 问题

`completion.py` Phase 1：无 F2F 时 `tick≥8` 仍 `completed` → 中屏空回合结束。  
Tier B 仅要求 `F2F≥1 OR observer≥1`，无法保证中屏体验。

#### 3.5.2 方案

**（1）F03 Phase 1/2/4 完成条件收紧**（`experience_hardening.enabled` 时）：

```python
# completion.py — Phase 1 增补（E1 落地后）
if is_experience_hardening() and task.phase == "Phase 1":
    if db.has_f2f_after(RECEPTION_PLACE, start, current_tick):
        return True
    if task.inject_status == INJECT_STATUS_FAILED:
        return True
    # 移除「纯 timeout completed」—— 延长至 start+12 仅作最终兜底
    if current_tick >= start + 12:
        return True
    return False
```

Phase 2：`jensen_private_room` F2F 优先（与 Phase 1 对称）。  
Phase 4：已有 §13.5；同步去掉「仅 timeout 完成」或延长至 12 tick。

**（2）Tier B 硬断言** — `test_m0_acceptance.py` T4d：

```python
# 原：F2F>=1 OR observer>=1
# 新（experience_hardening enabled）：
if len(public) < 1:
    raise TestFailure("Tier B: Phase 1 must have ≥1 F2F in public_messages")
# 附加：
if count_rdc(from="接待前台", to="Jensen") > 2:
    raise TestFailure("Tier B: reception RDC spam")
```

**（3）E1 fallback 与 F03 协同**：若走 scripted F2F，F03 应能检测到 F2F 并正常 completed（无需等 12 tick）。

#### 3.5.3 验收

- 有 Key 时 Phase 1 E2E：**F2F≥1** 硬失败。
- 无 F2F 时 processing 持续至 tick 12 或 fallback 触发（不应提前 completed）。

---

### E6 — 会话卫生 + Phase 4 E2E 冒烟（P2）

#### 3.6.1 问题 A：`session/start` 不清 `async_state`

- `session/reset` 调用 `clear_async_state`；**`session/start` 不调用**。
- F11 `runtime.json` 残留 → `sync_runtime_state` 把旧 `player_turn=4` 覆写 cookie → 误触发 `bad_reject`。

#### 3.6.2 方案 A

```python
# http/routes.py session_start 或 lifecycle.create_session 路径
from agent_world.hbm_demo.features.f11_live_turn_sync.task_state import clear_async_state

@hbm_bp.route(".../session/start", ...)
def session_start(...):
    clear_async_state(gs.get_sim_dir())  # 新增
    hbm = gs.create_session()
    ...
```

`test_m0_acceptance.start_stack` 同步删除 `async_state/runtime.json`（与 world.db 一致）。

#### 3.6.3 问题 B：Phase 4 无自动化 E2E

dev_log/24 §12.2 Turn 21–25 仍为人工项。

#### 3.6.4 方案 B — **`test_f07_e_phase4_smoke`**

脚本内（不跑 25 Turn 全剧情）：

1. `session/reset`
2. 构造 session：`phase=Phase 4`, `place_id=negotiation_room`, `player_turn=21`（**测试专用 HTTP 参数或 internal helper**）
3. IPC MOVE CEO 4/5/6 → `nvidia_reception`；Jensen @ `negotiation_room`
4. `player-turn` 一句终局台词
5. 断言：`inject` 仅 Agent 2；`public_messages` F2F≥1；VP 无消息；CEO 不在谈判室

可选：在 `player-turn` 增加 **仅测试环境** 的 `debug_session_overlay`（`FLASK_ENV=development`  gated），避免生产误用。

#### 3.6.5 验收

- 连续两次 `session/start` 不触发 Turn 4 bad_end。
- Phase 4 smoke 测试 PASS。

---

## 4. 实施分期（F07-E1 → E3）

| 阶段 | 内容 | 预估 | 依赖 |
|------|------|------|------|
| **F07-E0** | E0 玩家可见 F2F + E6 session 卫生 | 0.5 PR | — |
| **F07-E1** | E1 首动 F2F 守卫 + scripted fallback + E5 部分 | 1 PR | **E0** |
| **F07-E2** | E2 RDC 配额 + Phase 1 inject 独占 tick | 1 PR | E1 |
| **F07-E3** | E3 本 Turn 摘要 + L6 闲聊分流 + E4 跑题抑制 | 1 PR | E1 |
| **F07-E5** | E5 F03 收紧 + Tier B 硬断言（与 E1 同 PR） | — | E0 |
| **F07-E6** | Phase 4 IPC 冒烟（与 E0 同 PR 或 E1 后） | — | — |

**建议合并顺序（v1.1）**：**Step1(E0+E6) → Step2(E1+E5) → Step3(E2) → Step4(E3+E4) → Step5(回归)**；**禁止跳过 E0**。

---

## 5. 测试计划（§12 增补）

### 5.1 自动化

```text
E1: Phase 1/2/4 — public_messages ≥ 1（Tier B 硬断言）
E2: Phase 1 — 前台→Jensen RDC ≤ 2
E3: Turn1 技术 + Turn2 玩梗 — Turn2 F2F 回应玩梗 OR 无新「80%」RDC
E4: Phase 1 — Jensen RDC 不含黑名单词（三星/roadmap） unless 玩家提及
E5: 无 F2F 时 tick<12 不 completed（mock DB）
E6: session/start ×2 不 bad_end；Phase 4 smoke
```

### 5.2 人工（保留）

| 阶段 | 检查点 |
|------|--------|
| Phase 1 | 中屏短句 + Observer 一条清晰 RDC 链 |
| Phase 2 | Jensen 先回玩家再 RDC VP |
| Phase 3 | 引用玩家技术词帮腔 |
| Phase 4 | 仅 Jensen 1v1；VP 在室不发言 |
| Turn 4/12/16/25 | 四节点不退化 |

---

## 6. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 首动守卫导致 Agent 永远不发 RDC | F2F 发出后解除守卫；fallback 保证下限 |
| inject 独占 tick 拖长 completed | F03 与 tick_count 上限 12 对齐 |
| scripted F2F 太「假」 | 模板仅 1 句；优先 LLM；模板含玩家关键词 |
| 测试 flaky | Tier B 允许 2 次 inject 重试；黑名单断言用 mock 单元 + E2E 分离 |
| 与 F07-D 行为差异 | `experience_hardening.enabled: false` 一键回滚 |

---

## 7. 预期效果（对齐原始需求）

| 原始诉求 | F07-D | F07-E 后 |
|----------|-------|----------|
| 玩家输入影响 Agent | Observer RDC 引用关键词 | + 中屏 F2F 强制回应本 Turn |
| 发言简短像真人 | L2/L6 已设 | + 重复 RDC 消除；跑题抑制 |
| Phase 控制谁行动 | L3/L5 ✅ | + tick 序更贴合剧情 |
| 玩梗也能推进 | 未稳定 | E3 闲聊分流 + Jensen 摘要 |
| Phase 4 仅 Jensen 对话 | inject/L3 ✅ | E1 保证 Jensen F2F；E6 E2E |

**目标**：体验评分从约 **70%** 提升至 **≥85%**（中屏 F2F 稳定、Observer 噪音可控、Turn 间因果清晰）。

---

## 8. 文件清单（预计新增/修改）

```text
features/f07_agent_control/
├── turn_control.yaml          # experience_hardening 块
├── tool_guard.py              # first_action_guard + rdc_quota
├── f2f_fallback.py            # 新建
├── inject_batch.py            # jensen player summary
├── pick_active.py             # inject_exclusive_ticks
├── player_response.py         # E3 L6
└── config.py                  # is_experience_hardening()

core/runner/
├── world_step.py              # batch_f2f_sent / passive temp
└── ipc_handlers.py            # 批状态初始化、fallback 触发

features/f03_action_result/
└── completion.py              # E5 收紧

features/f01_session/ + http/
└── routes.py                  # session/start clear_async_state

scripts/
└── test_m0_acceptance.py      # T4d/T4e F07-E 断言
```

---

## 9. 与 dev_log/24 的关系

- dev_log/24 **F07-A~D** 解决「架构性失控」（全员 tick、乱 MOVE、无知识库）。
- 本 log **F07-E** 解决「**玩家可感知交互**」最后一英里。
- 不重复实施 L3/L4/L5 主矩阵；仅在同一 Feature 目录下 **增量** `experience_hardening` 子模块。
- dev_log/24 §13.1「选项 A：必须先 speak_to_local」由 **E1 硬约束**  finally 兑现。

---

## 10. v1.1 深度审查（代码锚点 · 2026-05-23）

> **结论**：v1.0 方向正确，但 **E1 若仅强制 `speak_to_local` 无法解决 Phase 1/2 中屏 F2F=0**——须先补 **E0 玩家可见 F2F 通道**。审查后修订实施顺序与实现细节如下。

### 10.1 关键发现：中屏 F2F 空的真正根因（比「LLM 不听话」更底层）

dev_log/27 §7 已指出 Agent 1 选 RDC 则中屏空；**v1.1 补充引擎机制**：

| 事实 | 代码锚点 | 后果 |
|------|----------|------|
| **玩家不是 Agent 实体** | Flask `player_memory` inject；无 `agent_id` | F2F 总线无「玩家」收件人 |
| **`speak_to_local` 仅写给同地点其他 Agent** | `FaceToFaceBus.send()`：`co_located = agents_at(place) - {sender}`；**空集则 return []、不落库** | Phase 1 前台独自在 `nvidia_reception` → **即使 LLM 正确调用 speak_to_local，DB 仍 0 条 F2F** |
| **中屏读法** | `fetch_f2f_history_at(place_id)` 查 `direct_message WHERE channel_type='F2F' AND place_id=?` | 只要有 sender 行即展示；**不依赖 recipient 是玩家** |
| Phase 2 同理 | Jensen @ `jensen_private_room` 通常仅 1 人 | 同问题 |
| Phase 4 例外 | Jensen + VP(3) 同在 `negotiation_room` | `speak_to_local` **可落库**（recipient=3），中屏可见 sender=2 内容 |

**v1.0 E1「首动 F2F 守卫」 alone 不够**：守卫只能逼 LLM 调用工具，**不能修复 FaceToFaceBus 空收件人**。

### 10.2 新增 E0 — 玩家可见 F2F 通道（P0 · E1 前置）

#### 方案：**HBM 专用 `player_facing_f2f`（不改引擎 FaceToFaceBus）**

新建 `features/f07_agent_control/player_facing_f2f.py`：

```python
PLAYER_RECIPIENT_ID = 0  # 约定：0 = 玩家（非引擎 Agent）

async def emit_player_facing_f2f(
    world_db, *, sender_id: int, place_id: str, content: str, t: int
) -> int:
    """Insert one F2F row visible to Flask public_messages (HBM-only)."""
    return await world_db.insert_message(
        sender_id=sender_id,
        recipient_id=PLAYER_RECIPIENT_ID,
        group_id=None,
        channel_type="F2F",
        content=content,
        place_id=place_id,
        attempted_at=t,
        arrive_at=t,
        delivered=1,
    )
```

**触发点（三选一，推荐 1+3）**：

1. **`HbmWorldStep` dispatch 后 hook**（主路径）：若本 tick 该 Agent 的 `speak_to_local` dispatch 成功但 FaceToFaceBus 返回 0 inserts（或检测 tick 内 place 无 co-agent），**追加** `emit_player_facing_f2f`。
2. **E1 scripted fallback**（兜底）：批末仍无 F2F → 调用同一 `emit_*`（v1.0 已有，改为必须走此 API 而非「假设 speak_to_local 有效」）。
3. **可选**：HBM kernel 包装 `FaceToFaceBus.send`，空 co_located 时自动 emit（侵入更小则优先 1）。

**验收**：Phase 1 仅 Agent 1 @ reception，`emit_player_facing_f2f(1, ...)` 后 `fetch_f2f_history_at` ≥1。

### 10.3 E1 修订 — 与 E0 协同

| v1.0 | v1.1 修订 |
|------|-----------|
| 强制 speak_to_local | 保留；但 **F2F 落库以 E0 hook/fallback 为准** |
| `batch_f2f_sent` 在 dispatch 后更新 | 在 **`emit_player_facing_f2f` 或 FaceToFaceBus 成功 insert 后** 标记 |
| `filter_tool_calls` 增参 `batch_f2f_sent` | 改为 **`BatchGuardState` 挂在 `HbmWorldStep`**，经 `agent._batch_guard_state` 传入（`turn_context` 只读不宜 mutate） |

**`filter_tool_calls` 现有行为注意**：当前对首个非法工具 **整批替换为单个 `do_nothing`**（L103）。首动守卫应 **在** `is_tool_allowed` 之前判断，逻辑顺序：

```text
experience_hardening → first_action_guard → rdc_quota → is_tool_allowed (matrix)
```

### 10.4 E2 修订 — tick 序实现锚点

`turn_context` 现有字段含 `inject_agent_ids`（`turn_context.py` L24），**无需新 IPC 字段**。

在 `HbmWorldStep` 增 `_batch_tick_index`（inject 批开始时置 0，每 `run_one_tick` +1），传入 `pick_active_ids`：

```python
if inject_exclusive_ticks.get(phase, 0) > batch_tick_index:
    inject_set = set(turn_context.get("inject_agent_ids") or [])
    return [aid for aid in primary if aid in inject_set]
```

### 10.5 E5 修订 — 与 tick_count 对齐

| 项 | 修订 |
|----|------|
| `resolve_inject_tick_count` | F07-E 启用时 Phase 1/2/4 返回 `max(n, 12)`（与 completion 兜底 tick 一致） |
| completion 兜底 | E0 fallback 在批末 tick 写入 F2F → 正常 `has_f2f_after` completed，**不必等 tick 12** |
| Tier B | E0+E1 就绪后再硬断言 `F2F≥1`（否则 CI 必 flaky） |

### 10.6 E6 修订 — Phase 4 smoke 无需 HTTP debug overlay

v1.0 提议 `debug_session_overlay` 过重。v1.1 改为与 `test_f07_d` 一致：

- **单元/半 E2E**：`HbmSession` + `send_inject_batch` + IPC MOVE CEO（测试内直接调 `ipc_helper`）
- **可选 HTTP E2E**：连续 `player-turn` 打满到 Turn 21（慢，放 nightly）

`session/start` 清 `async_state` **仍必要**，与 Phase 4 测试方式无关。

### 10.7 v1.0 方案可行性总表（审查后）

| 项 | v1.0 可落地？ | v1.1 结论 |
|----|--------------|-----------|
| E1 首动 F2F 守卫 | ⚠️ 不足 | **+ E0 后可落地** |
| E2 RDC 配额 | ✅ | 可行；与 E1 批状态共用 `BatchGuardState` |
| E2 inject 独占 tick | ✅ | 需 `_batch_tick_index` |
| E3 Jensen 摘要 notification | ✅ | `script_engine.notify_agent(2, ...)` 已存在 |
| E4 被动降温 | ✅ | `world_step._run_single_agent` 已有 batch llm 覆盖点 |
| E5 F03 收紧 | ⚠️ | 依赖 E0；tick 上限改 12 需同步 `resolve_inject_tick_count` |
| E6 session/start | ✅ | 单行 `clear_async_state` |
| E6 Phase 4 smoke | ⚠️ | 改为 IPC 直测，去掉 debug overlay |

### 10.8 修订实施顺序（推荐 5 步）

```text
Step 1 — F07-E0+E6（基础卫生 + F2F 通道）
  • player_facing_f2f.py + world_step dispatch hook
  • session/start → clear_async_state
  • start_stack 删 async_state/runtime.json
  • 单元：emit 后 fetch_f2f ≥1

Step 2 — F07-E1+E5（守卫 + 完成语义 + 测试）
  • BatchGuardState + first_action_guard + f2f_fallback
  • completion 收紧 + resolve_inject_tick_count(12)
  • Tier B：F2F≥1 硬断言

Step 3 — F07-E2（RDC 去重 + tick 序）
  • rdc_quota + inject_exclusive_ticks

Step 4 — F07-E3+E4（Turn 优先 + 跑题抑制）
  • Jensen 摘要 notification + L6 闲聊分流
  • 被动降温 + notification 收窄

Step 5 — 全量回归 + 人工 Turn 1/2/21 验收
  • test_m0_acceptance 全 PASS
  • 体验评测：Turn1 技术 + Turn2 玩梗 + Phase4 smoke
```

---

**文档版本**：v1.1 · 2026-05-23（深度审查修订）  
**下一步**：按 **Step 1 → Step 5** 实施；**禁止跳过 E0 直接做 E1**。
