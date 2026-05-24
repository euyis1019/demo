# 开发日志 24：HBM Demo Agent 行为控制整合方案

**记录时间**：2026-05-24  
**分支**：`jensen-hwang-demo`  
**状态**：**设计定稿**；**运行时实现已自 Demo 移除**（待按本文从头重建）  
**关联文档**：
- 目录与运行机制 → [`22_HBM_Demo目录结构与功能说明.md`](./22_HBM_Demo目录结构与功能说明.md)
- 25 轮参考台词 → [`19_HBM_Demo_25轮参考台词.md`](./19_HBM_Demo_25轮参考台词.md)
- 启动 / 重置 → [`23_HBM_Demo启动重置与运行指南.md`](./23_HBM_Demo启动重置与运行指南.md)

---

## 1. 问题定义

### 1.1 现象

玩家在 **Phase 1 / Turn 1–3**（前台 `nvidia_reception`）发言后，出现与剧情阶段不符的 Agent 行为，例如：

- 谈判室三大 CEO 在 GRP 群聊中长篇密谋；
- Sam Altman（`openai_hq`）`request_move` 到前台；
- Jensen 尚未出场，但对话中已出现「Jensen 亲自来见玩家」类叙述；
- 右栏 Observer 消息爆炸，中屏 F2F 反而被淹没或不符合预期。

### 1.2 根因（架构层，非单纯 prompt 写不好）

| 层级 | 现状 | 后果 |
|------|------|------|
| **Inject 目标** | `PHASE_INJECT_AGENTS` 已按 Phase 限制（Phase 1 仅 Agent 1） | ✅ 玩家台词只 inject 给前台 |
| **Tick 活跃 Agent** | `WorldStep.scheduler=None` → **每 tick 全部 7 Agent 跑 LLM** | ❌ 谈判室 / OpenAI 远端 Agent 同步「抢戏」 |
| **工具约束** | LLM 可自由调用 `request_move` / GRP / RDC | ❌ 文字 prompt 无法可靠禁止 MOVE |
| **阶段上下文** | Phase/Turn 规则主要在 Flask `routing.py`；Runner Agent **看不到**硬约束 | ❌ yaml soul 与真实 session 状态脱节 |
| **LLM 参数** | `temperature: 0.85` | ❌ 创造性偏高，加剧随机加戏 |

**结论**：需要 **分层防御（Defense in Depth）**，将 prompt、参数、tick 范围、动态约束、引擎硬约束整合为一套方案，而非单独依赖某一手段。

---

## 2. 设计目标

| 目标 | 可验收标准 |
|------|------------|
| **阶段守序** | Phase 1 仅前台 F2F + 可选 RDC(1→2)；右栏无谈判室 GRP |
| **地点守序** | Turn 16 前 Sam 不得离开 `openai_hq` |
| **Turn 守序** | Turn 4 前无 Jensen 前台出场；Turn 12 前无 Phase 3 群战 |
| **可维护** | 阶段规则集中配置（单文件矩阵），不散落在 7 份 soul 长文 |
| **可渐进落地** | 分 3 个实现 Phase，每步可独立验收、可回滚 |
| **不破坏主线** | 节点 A/B/C/D、Turn 16 广播 + Sam、Turn 25 结局行为保持不变 |

---

## 3. 整合方案总览：五层控制栈

```text
┌─────────────────────────────────────────────────────────────┐
│ L5 引擎硬约束（最稳）                                         │
│     工具白名单 / MOVE 拦截 / Phase 外 Agent 不 tick           │
├─────────────────────────────────────────────────────────────┤
│ L4 结构化回合上下文（「轻量知识库」）                            │
│     每轮 inject：Phase/Turn/允许工具/禁止行为/参考台词片段      │
├─────────────────────────────────────────────────────────────┤
│ L3 Tick 活跃 Agent 白名单                                     │
│     每 player-turn 仅指定 Agent 参与 run_one_tick LLM         │
├─────────────────────────────────────────────────────────────┤
│ L2 LLM 参数                                                   │
│     temperature / max_tokens 按 Phase 或全局下调               │
├─────────────────────────────────────────────────────────────┤
│ L1 静态 Prompt（yaml soul）                                   │
│     角色性格 + 简短阶段原则（不堆叠长篇规则）                    │
└─────────────────────────────────────────────────────────────┘
         玩家 player-turn
              │
              ▼
    Flask 组装 TurnContext ──IPC inject_batch──▶ Runner
              │                                    │
              │                                    ├─ L3 设置本批 tick 白名单
              │                                    ├─ L4 写入 inject + notification
              │                                    ├─ L2 使用 yaml 温度
              │                                    └─ L5 工具过滤 / MOVE 拦截
              ▼
         API 2 返回符合阶段的 F2F/RDC/GRP
```

**原则**：上层（L1–L2）引导模型；下层（L3–L5）保证底线。**任何一层单独启用都有收益；五层齐开达到演示级稳定。**

---

## 4. 核心配置：Turn 控制矩阵（单文件真相源）

建议新增 **`agent_world/hbm_demo/turn_control.yaml`**（或 `turn_control.py` 内嵌常量），由 Flask 与 Runner **共用同一份逻辑**（Runner 通过 inject payload 接收快照，避免双进程读不同文件）。

### 4.1 每 Phase 活跃 Agent（L3）

| Phase | 活跃 Agent ID | 说明 |
|-------|---------------|------|
| Phase 1 | `[1]` | 仅接待前台 |
| Phase 2 | `[2]` | 仅 Jensen；Tech VP 仅 RDC 被动回复（见 4.3） |
| Phase 3 | `[2, 3, 4, 5, 6]` | 谈判室全员；Sam 在 Turn 16 后激活 |
| Phase 4 | `[2, 3]` | 终局谈判 |

**特殊 Turn 覆盖**：

| Turn | 追加/覆盖 | 说明 |
|------|-----------|------|
| 16 | 激活 Agent 7；inject Sam 搅局文本 | 现有 `TURN16_BROADCAST` + `TURN16_SAM_TEXT` 保留 |
| 4 | Phase 1 仍仅 `[1]`；Bad End 早退不变 | 节点 A 在 API 1 判定，不依赖 Agent MOVE |

### 4.2 每 Phase 工具白名单（L5）

工具名与 `demo_agent.TOOLS` 对齐：

| Phase | Agent | 允许 | 禁止 |
|-------|-------|------|------|
| 1 | 1 | `speak_to_local`, `send_message`, `do_nothing`, `update_state` | `request_move`, `send_to_group`, `relation_change` |
| 1 | 2–7 | `do_nothing` | 其余全部 |
| 2 | 2 | `speak_to_local`, `send_message`, `do_nothing`, `update_state` | `request_move`, `send_to_group` |
| 2 | 3 | `send_message`（仅回复 Jensen RDC）, `do_nothing` | `speak_to_local`, `request_move`, GRP |
| 3 | 2–6 | 全工具（含 GRP/RDC/MOVE，受节点 C 前地点约束） | — |
| 3 | 7 | Turn ≥16：`send_message`, `do_nothing`；Turn ≥16 且剧情需要：`request_move` | Turn <16：全部除 `do_nothing` |
| 4 | 2, 3 | 同 Phase 3 子集 | CEO 不再 tick |

**MOVE 硬规则（L5 拦截表）**：

| agent_id | 条件 | 动作 |
|----------|------|------|
| 7 (Sam) | `player_turn < 16` | 拒绝任何 `request_move` |
| 4,5,6 (CEO) | `phase != Phase 3` | 拒绝 `request_move` |
| 2 (Jensen) | `phase == Phase 1` | 拒绝 `request_move` |
| 1 (前台) | 任意 | 拒绝 `request_move`（玩家由 session.place_id 驱动，非 Agent MOVE） |

### 4.3 Inject 目标（现有 + 不变）

保持 `routing.PHASE_INJECT_AGENTS`；L4 的 **系统约束文本** inject 到与 L3 相同的 Agent 集合。

### 4.4 LLM 参数（L2）

| 项 | 现值 | 建议值 | 备注 |
|----|------|--------|------|
| `hbm_scenario.yaml` → `llm.temperature` | 0.85 | **0.65**（Phase 1–2）；Phase 3 可 **0.70** | 可在 TurnContext 中按 phase 覆盖 |
| `llm.max_tokens` | 500 | **350**（Phase 1 前台） | 减少长篇群聊倾向 |
| 打分 / immediate_msg | 0.3 / 0.8 | 不变 | 与 Agent 抢戏无关 |

---

## 5. 分层实现规格

### 5.1 L1 — 静态 Prompt 精简（`hbm_scenario.yaml`）

**原则**：soul 只保留 **性格 + 长期目标**；阶段规则迁到 L4 动态 inject。

各 Agent soul 末尾统一增加 **一句** 原则性说明（示例）：

```text
【阶段服从】你收到「系统约束·Turn N」时，必须优先遵守；与 soul 冲突时以系统约束为准。
违反约束的 MOVE/群聊将被引擎拒绝。
```

**前台 Agent 1** 保留现有 RDC 汇报规则；删除或缩短易误导的「汇报后可以 F2F」类模糊表述，改为 L4 每轮明确。

### 5.2 L2 — Temperature / max_tokens

- 配置写在 `hbm_scenario.yaml` 或 `turn_control.yaml` 的 `llm_defaults` / `llm_by_phase`。
- `kernel.build_kernel` 创建 `HbmAgent` 时读取；若 TurnContext 带 `temperature_override`，本批 tick 临时覆盖（可选，Phase 2+ 再做）。

### 5.3 L3 — Tick 活跃 Agent 白名单

**数据流**：

```text
game_service.handle_player_turn
  → routing.build_inject_payload(session, player_text, turn_context)
  → ipc inject_batch { events, tick_count, turn_context: { phase, player_turn, active_agent_ids } }
  → ipc_handlers.handle_inject_script_event
  → world_step.set_tick_context(turn_context)   # 新增
  → for _ in range(tick_loops): run_one_tick()
  → world_step.clear_tick_context()
```

**实现要点**：

- 在 `HbmWorldStep` 重写 `_pick_active(t)`：若存在 `tick_context.active_agent_ids`，仅返回该列表与「有未读消息需回复」的被动 Agent（Phase 2 Tech VP RDC，可选）。
- `scheduler=None` 保持不变，避免动引擎壳。

**Phase 1 预期**：每 player-turn 的 8 tick 内，**只有 Agent 1** 调用 DeepSeek API；Runner 日志中无 Agent 2–7 的 httpx 请求。

### 5.4 L4 — 结构化回合上下文（轻量知识库）

**TurnContext 文档**（每轮由 Flask 生成，JSON 随 inject 传入 Runner，并写入 inject 文本）：

```json
{
  "phase": "Phase 1",
  "player_turn": 2,
  "place_id": "nvidia_reception",
  "active_agent_ids": [1],
  "allowed_tools": ["speak_to_local", "send_message", "do_nothing"],
  "forbidden_actions": ["request_move", "send_to_group"],
  "narrative": "玩家在前台；Jensen 在谈判室与三家 CEO 谈判，未出场。",
  "reference_hint": "可参考：前台礼貌接待，技术亮点则 RDC 汇报 Jensen。"
}
```

**注入方式（双通道）**：

1. **dialogue_injection** 文本前缀（已有 `format_player_dialogue` 链路）：
   ```text
   【系统约束·Phase 1 Turn 2】
   地点：nvidia_reception。允许工具：speak_to_local, send_message, do_nothing。
   禁止：request_move、群聊、替 Jensen 做决定、描写 Jensen 已见玩家。
   玩家说：……
   ```

2. **scripted_notification**（`hbm_agent._observation_to_text` 已支持）：对本批活跃 Agent 附加同一段「系统约束」。

**与 dev_logs/19 的关系**：

- 从 [`19_HBM_Demo_25轮参考台词.md`](./19_HBM_Demo_25轮参考台词.md) 按 Turn 抽取 **1–2 句 reference_hint** 写入 TurnContext（非全文，控制 token）。
- 不引入向量库；MVP 用 **Turn → hint 字典** 即可。

**新增模块建议**：`agent_world/hbm_demo/turn_context.py`

- `build_turn_context(session: HbmSession) -> dict`
- `format_constraint_prefix(ctx) -> str`
- `reference_hint_for_turn(turn: int, phase: str) -> str`

### 5.5 L5 — 引擎硬约束

**5.5.1 工具白名单（`hbm_agent.py`）**

- 在 `perform_action_by_llm` 解析 tool_calls 后、dispatch 前，根据 `turn_context` + `turn_control` 矩阵过滤非法工具。
- 非法工具：记录 debug 日志，替换为 `do_nothing` 或向 LLM 返回「工具不可用」（二选一，推荐 **静默 do_nothing** 以免 extra LLM 轮次）。

**5.5.2 MOVE 拦截（`hbm_agent.py` 或 `ActionDispatcher` 包装）**

- 对 `request_move` 查 **MOVE 硬规则表**（§4.2）。
- 拒绝时不写 DB、不更新 `place_store`。

**5.5.3 Phase 外 Agent 不 tick（与 L3 合并）**

- L3 白名单即最强硬约束；L5 工具过滤作为 **双保险**（防止白名单配置遗漏）。

---

## 6. 与现有剧情节点的兼容性

| 现有机制 | 整合方案中的处理 |
|----------|------------------|
| 节点 A Turn 4 | Flask 判定 Bad End / Phase 2；**IPC MOVE Jensen** 仍由 `routing.apply_routing` 发起，**不受** Agent 自主 MOVE 限制 |
| 节点 B Turn 12 | Tech VP 正面 RDC：Phase 2 末允许 Agent 3 **仅 RDC 回复** 被动 tick（L3 例外列表） |
| Turn 16 广播 | 保持 `broadcast_helper` + Sam inject；Turn 16 将 Sam 加入 L3 白名单 + 放开 RDC/MOVE |
| 节点 C / D | Phase 4 白名单 `[2,3]`；Turn 25 结局分类不变 |
| `check_action_complete` | 不变；Phase 1 仍 RDC(1→2) 或 F2F 或 tick 超时完成 |
| 重开 `session/reset` | 重置后 TurnContext 回到 Phase 1 Turn 1 默认矩阵 |

---

## 7. 实施路线图（三阶段）

### Phase A — 快速见效（约 0.5–1 天）

| 项 | 内容 | 改动面 |
|----|------|--------|
| A1 | `temperature` 0.85 → 0.65 | `hbm_scenario.yaml` |
| A2 | 新增 `turn_control.yaml` + `turn_context.py` 骨架 | 新文件 |
| A3 | L4：`build_inject_payload` 增加系统约束前缀 | `routing.py`, `game_service.py` |
| A4 | L1：yaml soul 精简 + 阶段服从一句 | `hbm_scenario.yaml` |

**验收**：Phase 1 Turn 1 右栏 GRP 条数显著下降（仍可能有 CEO 发言则进入 Phase B）。

### Phase B — 治本（约 1–2 天）

| 项 | 内容 | 改动面 |
|----|------|--------|
| B1 | L3：`HbmWorldStep._pick_active` + inject 传 `turn_context` | `world_step.py`, `ipc_handlers.py`, `ipc_helper.py`, `routing.py` |
| B2 | L5：工具白名单过滤 | `hbm_agent.py` |
| B3 | L5：MOVE 硬规则拦截 | `hbm_agent.py` |
| B4 | dev_logs/19 → Turn hint 字典 | `turn_context.py` |

**验收**：

- Phase 1 Turn 1：Runner 日志 **仅 Agent 1** 有 DeepSeek 请求；
- 右栏 **0 条 GRP**（或仅历史残留为 0）；
- Sam **无 MOVE** 记录；
- 中屏有前台 F2F 或 RDC(1→2)。

### Phase C — 打磨（约 0.5–1 天）

| 项 | 内容 |
|----|------|
| C1 | Phase 2 Tech VP 被动 RDC tick 例外 |
| C2 | Phase 3 略调高 temperature / max_tokens |
| C3 | 结构化日志：`turn_context` 写入 `hbm` 日志前缀 |
| C4 | 可选：Turn 1–3 自动化回归脚本（curl E2E + 断言 GRP 数量） |

**验收**：按 dev_logs/19 人工试玩 Turn 1–4、Turn 16 无严重抢戏；节点 A Bad End 仍触发。

---

## 8. 测试与回归清单

### 8.1 自动化（Phase C）

```text
1. session/start → player-turn (Phase 1 台词) → action-result completed
2. 断言 observer_messages 中 GRP 数量 == 0
3. 断言 world.db 无 agent 7 的 location 变更（Turn 1）
4. session/reset → 重复上述
```

### 8.2 人工（必做）

| Turn | 检查点 |
|------|--------|
| 1–3 | 中屏以前台 F2F 为主；右栏最多 RDC(1→2) |
| 4 低分 | Bad End 仍出现 |
| 4 高分 | 进 Phase 2，地点变 `jensen_private_room` |
| 16 | Sam 搅局 RDC / 广播可见 |
| 重开 | 左栏「重开」后恢复 Turn 1，无旧消息 |

### 8.3 失败判定

- Phase 1 出现 **SK/Micron/Samsung GRP** → L3 未生效或白名单配置错误；
- Sam 出现在 `nvidia_reception` 且 Turn < 16 → L5 MOVE 规则未生效；
- 前台从不 F2F → 与 API 欠费 / prompt 冲突，需单独排查（见 dev_logs/23）。

---

## 9. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 约束过严，NPC 完全不说话 | L3 白名单内 Agent 保留完整工具；L5 只禁 MOVE/GRP 不禁 F2F/RDC |
| Turn 16 Sam 无法搅局 | Turn 16 使用 **Turn 覆盖表** 显式加入 Agent 7 + 放开工具 |
| 双进程 phase 不同步 | TurnContext 仅信 Flask inject 快照，Runner 不读 session cookie |
| 回滚 | `turn_control.yaml` 设 `enabled: false` 开关；或 Git revert Phase B 提交 |

---

## 10. 涉及文件一览（实现时）

| 文件 | 层级 | 变更类型 |
|------|------|----------|
| `hbm_scenario.yaml` | L1, L2 | 修改 |
| `turn_control.yaml` | L3–L5 | **新建** |
| `turn_context.py` | L4 | **新建** |
| `routing.py` | L3, L4 | 修改 |
| `game_service.py` | L4 | 修改 |
| `world_step.py` | L3 | 修改 |
| `hbm_agent.py` | L5 | 修改 |
| `ipc_handlers.py` | L3 | 修改 |
| `ipc_helper.py` | L3 | 修改（payload 类型） |
| `kernel.py` | L2 | 可选（按 phase 读温度） |

**不修改**：`agent_world/demo/`、引擎核心 `world/dispatcher.py`（除非 L5 选择在 dispatcher 包装层做 MOVE 拦截，优先 hbm_demo 内完成）。

---

## 11. 方案命名与状态

- **方案代号**：**ABCS**（Agent Behavior Control Stack，五层控制栈）
- **本文档版本**：v1.0 · 2026-05-24
- **下一步**：评审本方案 → 按 Phase A → B → C 实施 → 更新 dev_logs/18 待办

---

*本文档为 Agent 行为失控问题的整合设计；**实现待重建**（原 `features/f07_agent_control/` 已自 Demo 移除）。*

---

## 12. 实施记录（M5 · 2026-05-24）

| Phase | 项 | 状态 |
|-------|-----|------|
| A | temperature 0.65、`turn_control.yaml`、`turn_context.py`、L4 约束前缀 | ✅ |
| B | L3 `HbmWorldStep._pick_active`、IPC `turn_context`、L5 tool/MOVE 拦截 | ✅ |
| C | Turn hint 字典、E2E GRP=0 断言、结构化 ABCS 日志 | ✅ |

回滚：`turn_control.yaml` 设 `enabled: false`。
