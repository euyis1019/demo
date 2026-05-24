# 开发日志 24：HBM Demo Agent 行为控制整合方案（ABCS / F07）

**记录时间**：2026-05-24（v1.1）· **v2.0 整合**：2026-05-25 · **v2.1 审查修补**：2026-05-25 · **v2.2 代码锚点审查**：2026-05-25 · **v2.3 上下文详述原则**：2026-05-25 · **v2.4 实施细节补强**：2026-05-25  
**分支**：`feature/f07-agent-behavior-control`（自已合并 F11 的 `jensen-hwang-demo` 拉出）  
**状态**：**设计定稿 v2.4** · 待按 Feature 分 PR 实施  
**Feature ID**：**F07 — Agent Behavior Control Stack（ABCS）**  
**前置 Feature**：**F11 Live Turn Sync**（已合并 `jensen-hwang-demo` @ `aa03d48`）

**关联文档**：
- 剧情原型与四 Phase 路由 → [`dev_docs/1_story_prototype.md`](../dev_docs/1_story_prototype.md)
- Feature 规划与目录规范 → [`26_HBM_Demo_Feature规划与代码结构重整方案.md`](./26_HBM_Demo_Feature规划与代码结构重整方案.md)
- 引擎与玩家干预全景 → [`27_agent_world引擎与HBM_Demo_Agent行为与玩家干预机制全景.md`](./27_agent_world引擎与HBM_Demo_Agent行为与玩家干预机制全景.md)
- 25 轮参考台词 → [`19_HBM_Demo_25轮参考台词.md`](./19_HBM_Demo_25轮参考台词.md)
- F11 增量同步 → [`28_HBM_Demo_F11_回合内增量同步方案.md`](./28_HBM_Demo_F11_回合内增量同步方案.md)

---

## 0. v2.0 整合摘要（相对 v1.1 的变化）

| 维度 | v1.1 | v2.0（本次） |
|------|------|-------------|
| **整体目标** | 抑制抢戏 / 乱 MOVE | **+ 强化玩家输入对 Agent 行为与台词的因果影响；对话更像真人、长短得当** |
| **Phase 1 活跃 Agent** | 仅 `[1]` | **`[1,2,3]` 主活跃 + `[4,5,6]` 低频被动**；Sam `[7]` 冻结 |
| **Phase 1 剧情** | 前台 RDC 报信 | **+ 前台非技术岗价值判断 → Jensen 评估 → Tech VP 交流 → Jensen 批准转场** |
| **移动策略** | 按 Phase 禁 MOVE | **Phase 1–2 全员禁止自主 MOVE**；转场仅 **F05 路由 IPC MOVE** |
| **知识库** | Turn hint 字典 | **混合模式定稿**：共享 Story Bible + Agent 角色片；**输入详述**（§6） |
| **温度** | 全局 0.65 | **按 Phase / 场景动态温度表（§7）** |
| **Phase 4** | `[2,3]` 活跃 | **Jensen 1v1 对话；Tech VP 留室旁听不发言**；CEO 移前台（§5.4） |
| **Feature 形态** | 建议 F07 | **确认为独立 Feature `features/f07_agent_control/`，分 F07-A/B/C/D 实施** |

### v2.2 增补（代码锚点审查）

| 维度 | 发现 | 处置 |
|------|------|------|
| **player_memory** | 仅 inject 目标写入；**跨 Turn 不清空**（仅 reset 清） | §19.2 每 Turn  scoped 记忆 |
| **Demo 通用 prompt** | `demo_agent._observation_to_text` 长篇「必须推进剧情」与玩家句**抢注意力** | §19.3 Hbm 专用 user prompt 尾 |
| **stale update_state 强制** | `stale_ticks≥5` 时**强制只许 update_state**，可盖过对玩家的 F2F | §19.4 有 player_memory 时禁用 |
| **LLM 参数** | `kernel.build_kernel` 固定 temperature；**批内不可变** | §19.5 turn_context 覆盖 |
| **F03 完成** | 当前 **RDC/GRP 即可 completed**；无 Phase 1/4 F2F 优先 | §13.2/13.5 待实现 |

### v2.3 增补（上下文详述 vs 输出短句）

| 维度 | 原则 |
|------|------|
| **Agent 说出口的话** | 短、像真人（L2 `max_tokens` 仍克制） |
| **Prompt + 知识库上下文** | 在满足剧情与阶段约束前提下 **尽可能详细**（§6.3–§6.7、§3.1） |
| **L1 soul** | 保留性格与长期目标；**阶段细则迁 L4**，但不删 soul 中与角色本质相关的细节 |

---

## 1. 问题定义与整体目标

### 1.1 现象（玩家视角）

- Agent 对话**不合理**：长篇大论、过于积极，不像人类交谈；
- **玩家输入影响弱**：Agent 各说各话，讨论内容与玩家发言脱节；
- Agent **随意移动**、随意切换地点，破坏阶段感；
- 对话**不推进剧情**，玩家感受不到「在和 Agent 交互」。

### 1.2 根因（架构层）

| 层级 | 现状 | 后果 |
|------|------|------|
| **Inject 目标** | `PHASE_INJECT_AGENTS` 限制玩家台词注入对象 | ✅ 玩家话只进指定 Agent memory |
| **Tick 活跃 Agent** | `scheduler=None` → **每 tick 全部 7 Agent 跑 LLM** | ❌ 非本阶段角色抢戏 |
| **工具约束** | LLM 可自由 `request_move` / GRP / RDC | ❌ prompt 无法可靠禁止 MOVE |
| **阶段上下文** | Phase 规则主要在 Flask；Runner **看不到**完整剧情状态 | ❌ soul 与 session 脱节 |
| **LLM 参数** | 温度偏高、max_tokens 偏大 | ❌ 输出冗长、过于「创作」 |
| **玩家因果** | inject 仅追加「玩家说：…」；非 inject 活跃 Agent **看不到玩家原话** | ❌ Phase 1 Jensen 仅能通过前台 RDC 间接感知 |
| **player_memory 持久** | 仅 `world_reset` 清空 `player_memory` | ❌ 多 Turn 后上下文稀释，旧玩家句干扰新 Turn |
| **Demo 观测 prompt** | 继承 `demo_agent` 10 条硬性规则 + 全工具列表 | ❌ 与「先回应玩家」目标竞争注意力 |
| **stale-state 守卫** | `DemoAgent._observation_to_text` 在 stale≥5 强制 update_state | ❌ 同批后期 tick 可能不对玩家 F2F |
| **F03 完成判定** | `check_action_complete`：F2F **或** RDC **或** GRP 即可 | ❌ Phase 1 可能 completed 但中屏无 F2F |

**结论**：需要 **分层防御 + 玩家中心叙事（Player-Centric）** 整合为 **F07 ABCS**，而非单改 prompt。

### 1.3 v2.0 设计目标（可验收）

| 目标 | 可验收标准 |
|------|------------|
| **阶段守序** | 各 Phase 仅矩阵允许的 Agent tick；Sam Phase 1–2 冻结 |
| **地点守序** | Phase 1–2 **零自主 MOVE**；转场仅 F05 节点触发 |
| **玩家可感知** | 每轮中屏 **≥1 条** 与玩家发言直接相关的 F2F（Phase 1–2）；Phase 4 严格 Jensen↔玩家 1v1 |
| **对话人味** | 前台/Jensen 短句为主；Phase 3 可略长但**必须引用玩家原话** |
| **上下文充分** | inject 前缀 **≥800 字**（世界态/剧情/角色目标齐全）；notification **≥400 字** |
| **剧情推进** | Phase 1 完成条件：Jensen 认可 → 路由进 Phase 2；与节点 A 对齐 |
| **不破坏主线** | 节点 A/B/C/D、Turn 16 广播 + Sam、Turn 25 结局保持 |

---

## 2. Feature 定位：能否 / 如何作为 Feature 开发

### 2.1 结论：**必须作为独立 Feature（F07）**

| 判据 | 说明 |
|------|------|
| **边界清晰** | L3 tick 白名单、L5 工具/MOVE 拦截、L4 知识库注入 — 均属「编排层约束 Runner 行为」，不改引擎核心 |
| **可独立回滚** | `turn_control.yaml` → `enabled: false` |
| **依赖关系** | F07 → F02（inject 传 turn_context）、F05（路由后更新 phase）、F00（world_step/hbm_agent）；**禁止** F06 → F07 |
| **与 F11 正交** | F11 管「何时展示消息」；F07 管「Agent 说什么、谁说话、能否 MOVE」 |

### 2.2 Git 与目录

```text
feature/f07-agent-behavior-control    ← 当前开发分支
features/f07_agent_control/           ← Feature 模块（待建）
```

```text
agent_world/hbm_demo/features/f07_agent_control/
├── __init__.py
├── turn_control.yaml          # L3–L5 矩阵 + enabled + 温度表
├── story_knowledge/           # L4 知识库（§6）
│   ├── shared/                # 各 Phase 共享「世界态」
│   └── agents/                # 各 Agent 角色知识片
├── turn_context.py            # build_turn_context, format_constraint_prefix
├── knowledge.py               # 组装 shared + agent 片段
├── tool_guard.py              # L5 白名单 / MOVE 拦截
├── pick_active.py             # L3 白名单 + 被动 tick 例外
├── llm_params.py              # L2 按 Phase 温度 / max_tokens
└── player_response.py         # 玩家中心约束模板（§8）
```

**注册**：`features/__init__.py` 增加 F07，`status: in_progress` → `implemented`。

---

## 3. 整合方案总览：六层控制栈（v2.0）

```text
┌─────────────────────────────────────────────────────────────┐
│ L6 玩家中心响应（v2.0 新增）                                   │
│     inject 强制「先回应玩家原话再行动」；reference 玩家关键词      │
├─────────────────────────────────────────────────────────────┤
│ L5 引擎硬约束                                                 │
│     工具白名单 / MOVE 拦截 / Phase 外 Agent 不 tick            │
├─────────────────────────────────────────────────────────────┤
│ L4 结构化知识库 + 回合上下文（**详述**：Story Bible + 角色片 + Turn 剧本） │
├─────────────────────────────────────────────────────────────┤
│ L3 Tick 活跃 Agent 矩阵（含被动 / 低频例外）                    │
├─────────────────────────────────────────────────────────────┤
│ L2 LLM 参数（按 Phase 动态温度 / max_tokens）                   │
├─────────────────────────────────────────────────────────────┤
│ L1 静态 Prompt（yaml soul：性格/长期目标；阶段细则下沉 L4）           │
└─────────────────────────────────────────────────────────────┘
         玩家 player-turn
              │
              ▼
    F07 build_turn_context ──IPC inject_batch + turn_context──▶ Runner
              │                                    │
              │                                    ├─ L3 pick_active
              │                                    ├─ L4 knowledge + 约束前缀
              │                                    ├─ L2 temperature_override
              │                                    └─ L5 tool_guard
              ▼
         F11 前端增量展示 F2F / Observer
```

**原则（v2.3）**：
- **输入详、输出短**：L4/L6/**知识库** 给足剧情与行为上下文；L2 限制 Agent **说出口** 的长度。
- L6/L4 **引导**模型理解玩家与角色；L3/L5 **保证**底线。

### 3.1 核心设计原则：输入详述 vs 输出短句

| 维度 | 目标 | 控制层 |
|------|------|--------|
| **System prompt（soul 等）** | 性格、长期目标、关系本质 **写清楚** | L1 `hbm_scenario.yaml` |
| **动态上下文（知识库 + 约束）** | 本 Phase/Turn **谁在哪、局势如何、该做什么、禁做什么、如何回应玩家** — **尽可能详细** | L4 + L6 + `story_knowledge/` |
| **Agent 实际发言（F2F/RDC/GRP）** | 短句、口语、1–4 句为主；Phase 3 可略长 | L2 `max_tokens` + overlay `speech_style` |

**禁止混淆**：为省 token 而压缩 **知识库/约束前缀**，会导致 Agent 不懂剧情、不回应玩家；应压缩的是 **模型输出**，不是 **输入上下文**。

---

## 4. 与剧情原型对齐（`dev_docs/1_story_prototype.md`）

四 Phase / 四地点 / 节点 A–D **不变**，v2.0 在 **Agent 行为矩阵** 与 **Phase 1/4 细节** 上细化：

| Phase | 原型 Turn | 玩家地点 | 原型 inject 目标 | v2.0 行为重点 |
|-------|-----------|----------|------------------|---------------|
| 1 | 1–4 | `nvidia_reception` | Agent 1 | **1,2,3 主活跃**；CEO 低频；Sam 冻结；**禁 MOVE** |
| 2 | 5–12 | `jensen_private_room` | Agent 2 | **primary `[2]`**；**passive `[3]`**（仅回 Jensen RDC）；CEO 低频；**禁 MOVE** |
| 3 | 13–20 | `negotiation_room` | 2–6 batch | 谈判室全员（Sam Turn16+ RDC）；**帮玩家**；可略长 |
| 4 | 21–25 | `negotiation_room` | 2（v2.1） | **Jensen 1v1**；Tech VP **留室旁听**；CEO 已离场 |

**与原型关系**：
- **Phase 1**：原型仅 inject Agent 1；v2.1 允许 Jensen/Tech VP **在谈判室** tick（RDC/低频 F2F），但不 MOVE、不抢前台中屏；
- **Phase 4**：原型 inject `[2,3]`、VP 留室；v2.1 **inject 仅 `[2]`**（玩家话只进 Jensen memory），Tech VP **物理留在 `negotiation_room` 但不 tick、不发言**（旁听位）；与原型「三人留室、VP 不抢戏」一致。**`dev_docs/1` 速查表在 F07-D 同步为 Agent 2 only**（§11 D5）。
- **节点 C**：现有 F05 **仅 MOVE CEO 4/5/6 → 前台**（代码已如此）；**不移动 Agent 3**。

---

## 5. 分 Phase 行为设计（v2.0 剧情规格）

### 5.1 Phase 1：前台的破局者（Turn 1–4）

**场景**：玩家在 `nvidia_reception`；谈判室三大 CEO 向 Jensen 施压（背景音，非主角）。

| 项 | 规格 |
|----|------|
| **主活跃 Agent（L3）** | `[1]` 前台、`[2]` Jensen、`[3]` Tech VP |
| **低频被动（L3 例外）** | `[4,5,6]`：仅当谈判室内有 **未读 F2F/RDC** 时可 tick；**仅** `speak_to_local`（短句回应同室）、`do_nothing`；**禁止 GRP** |
| **冻结** | `[7]` Sam — 不 tick、不 RDC |
| **移动** | **全员禁止 `request_move`**；玩家进私人会议室仅由 **节点 A**（F05 IPC MOVE）触发 |
| **inject 目标** | 保持 `[1]`（玩家台词进前台 memory）；Jensen/VP 通过 L4 知识库知悉「前台正在接待」 |

**角色任务与发言风格**：

| Agent | 任务 | 发言要求 |
|-------|------|----------|
| **1 前台** | 判断玩家是闲聊还是有价值技术；**不懂深技术** | **短句** F2F 对玩家；有价值则 **RDC→2** 简报（「有人带了…可能很重要」），不展开技术细节 |
| **2 Jensen** | 听前台/RDC + 自行判断；可与 Tech VP RDC 交流 | 短句、商务口吻；**不描写已来前台**；认可后 RDC→1「请到私人会议室」、RDC→3「你留在这里陪 CEO」 |
| **3 Tech VP** | 被 Jensen 问及时 **RDC 回复** 技术可行性（被动 tick） | 1–3 句；偏谨慎 |
| **4–6 CEO** | 谈判室背景压力 | **偶尔** 1 句 F2F 互怼或回应同室；不联系玩家、不 GRP 长篇 |

**Phase 1 完成（进 Phase 2）**：
- **硬条件（F05 不变）**：Turn 4 节点 A — `Vision+Execution≥15`；未达标 → Bad End（inject 前返回 `game_over`）。
- **软引导（F07 L4）**：Turn 1–3 知识库提示前台/Jensen「评估玩家价值」；Turn 4 提示 Jensen「若指标达标则批准转场」。
- **效果**：F05 `MOVE_AGENT` Jensen → `jensen_private_room`；session `place_id` → 私人会议室；Phase → 2。

**中屏 UX**：仅展示 `nvidia_reception` F2F → **前台必须 `speak_to_local`**（§13.1 保留）。

---

### 5.2 Phase 2：私密审查（Turn 5–12）

**场景**：玩家与 Jensen 在 `jensen_private_room`；谈判室仍有人，但 **地点不变**。

| 项 | 规格 |
|----|------|
| **主活跃** | `[2]` Jensen |
| **被动 tick** | `[3]` Tech VP — 仅在有 Jensen→VP 未读 RDC 时 tick（§13.3） |
| **冻结** | `[1]` 前台 |
| **低频被动** | `[4,5,6]` 同 Phase 1 规则，**频率更低**（矩阵 `passive_tick_probability: low`） |
| **冻结** | `[7]` Sam |
| **移动** | **全员禁止自主 MOVE** |
| **Jensen 通信** | **仅 RDC → Agent 3**；禁止 GRP、禁止 F2F 对 CEO |
| **Tech VP** | 回复 Jensen RDC；可与 CEO **低频** RDC/F2F（不帮玩家直接对话） |

**玩家交互目标**：
- 玩家 **不必** 讲高深技术；玩梗、故事、愿景均可；
- L6 约束：Jensen **每轮必须先回应玩家原话**（同意/质疑/追问），再 `update_state` 或 RDC；
- 发言 **2–4 句** 为宜，急躁、时间紧（参考 dev_docs/1 §Phase 2）。

**进 Phase 3**：节点 B（Turn 12）— `Execution≥20` + Tech VP 正面 RDC（现有 F05 逻辑不变）。

---

### 5.3 Phase 3：舌战群儒（Turn 13–20）

**场景**：`negotiation_room` 全员；前台冻结；Sam 远程。

| 项 | 规格 |
|----|------|
| **主活跃** | `[2,3,4,5,6]` |
| **冻结** | `[1]` |
| **Sam `[7]`** | Turn &lt;16 冻结；Turn ≥16：**仅 RDC** 搅局（现有 Turn16 inject 保留） |
| **移动** | CEO 在节点 C 前 **禁止 MOVE**；Jensen/VP 不随意 MOVE |
| **NVIDIA 阵营** | Agent 2、3 **帮玩家圆场**；话可略长（max_tokens↑）但 **须引用玩家刚才的观点** |

**Turn 16**：广播 + Sam inject（F05 不变）。

**进 Phase 4**：节点 C — `Burnout<80` & `Vision≥30`；CEO 4/5/6 **IPC MOVE** → `nvidia_reception`（**F05 现有逻辑，不移动 Agent 3**）。

---

### 5.4 Phase 4：一对一终局（Turn 21–25）

**场景**：玩家、Jensen、Tech VP 同在 `negotiation_room`（对齐 `dev_docs/1`）；三大 CEO 已被请至前台。

| 项 | 规格 |
|----|------|
| **主活跃（L3）** | **仅 `[2]` Jensen** — 唯一跑 LLM 的 Agent |
| **旁听（L3 新态）** | **`[3]` Tech VP** — **留在谈判室**（节点 C 后位置不变），**不 tick、不 inject、不发言**；L4 知识库标注「旁听，禁止输出」 |
| **冻结** | `[1,4,5,6,7]` — 不 tick（CEO 已在 `nvidia_reception`） |
| **路由（节点 C）** | 仅 MOVE Agent **4/5/6** → `nvidia_reception`（与现有 `routing.py` 一致） |
| **交互模式** | **严格 1v1**：玩家一句 → Jensen 一句；L6 禁止 Jensen 长篇独白开场 |
| **inject** | **`[2]` only**（`PHASE_INJECT_AGENTS["Phase 4"]` 由 `[2,3]` 改为 `[2]`） |
| **中屏 F2F** | 仅 `negotiation_room` 内 Jensen↔玩家；VP 无 F2F/RDC 输出 |
| **结局** | Turn 25 节点 D（F05 不变） |

**Tech VP 旁听的意义**：符合原型「三人留室」的空间感；VP 不出声、不 inject，避免抢 Jensen 终局戏；若未来要在 Observer 展示 VP 内心 OS，可仅读 `update_state` 快照（**非 MVP**）。

---

## 6. 知识库方案：**混合模式（定稿）**

> **决策**：采用 **Shared Story Bible + Agent Overlay** 混合知识库，不使用纯共享或纯分 Agent 方案。

### 6.1 选项对比（决策依据）

| 维度 | **共享知识库** | **分 Agent 知识库** | **混合（定稿）** |
|------|---------------|---------------------|------------------|
| 世界态一致 | ★★★★★ | ★★☆☆☆ | ★★★★★ |
| 角色沉浸 | ★★☆☆☆ | ★★★★★ | ★★★★☆ |
| Token / 维护 | 中 | 差 | **优** |

### 6.2 目录与文件结构

```text
story_knowledge/
├── shared/
│   ├── phase_1.yaml    # 世界态：谁在哪、当前冲突、禁止 MOVE
│   ├── phase_2.yaml
│   ├── phase_3.yaml
│   └── phase_4.yaml    # 含「VP 留室旁听、不发言」
├── agents/
│   ├── agent_1.yaml    # 前台：非技术、汇报模板、短句
│   ├── agent_2.yaml    # Jensen：Phase 目标、对谁 RDC
│   ├── agent_3.yaml    # Tech VP：Phase 4 追加 silent_observer: true
│   └── agent_{4..7}.yaml
├── turn_hints.yaml     # Turn→剧本片段（来自 dev_logs/19，可 3–8 句/ Turn）
└── glossary.yaml       # 可选：HBM/技术/人名术语表，shared 引用
```

### 6.3 上下文预算（v2.3：详述优先）

> **原则**：在模型 context window 允许范围内 **尽量写满有效信息**；仅当超长时再按优先级裁剪（§6.7）。

| 片段 | 建议篇幅 | 必须包含 |
|------|----------|----------|
| `shared/phase_*.yaml` → `world_state` | **200–400 字** | 地点、在场人物、当前冲突、与玩家相关的局势 |
| `shared/phase_*.yaml` → `scene_atmosphere` | **80–150 字** | 气氛、时间压力、谈判/前台背景音 |
| `shared/phase_*.yaml` → `forbidden_actions` | **80–120 字** | 本 Phase 禁止 MOVE/GRP/抢戏等 |
| `shared/phase_*.yaml` → `plot_beats` | **100–200 字** | 本 Phase 剧情要点（对齐 `dev_docs/1`） |
| `agents/agent_*.yaml` → 常驻字段 | **150–250 字** | 角色定位、说话习惯、关系网、对玩家态度 |
| `agents/agent_*.yaml` → `phase_overrides` | **100–200 字/Phase** | 本 Phase 具体目标、对谁说话、示例句 |
| `turn_hints.yaml` 单 Turn | **80–200 字** | 参考台词、预期动作、节点提示 |
| L6 玩家回应约束 | **80–120 字** | 先回应玩家、复述关键词、输出长度上限 |
| **inject 目标合计** | **约 800–1200 字** + 玩家原话 | — |
| **notification（非 inject 活跃 Agent）** | **约 400–700 字** | shared 全文 + 角色摘要 |

**不引入向量库**；结构化 YAML + Turn 字典即可，重点是 **内容完整** 而非极简。

**注入通道**（双通道，与 v1.1 一致）：
1. **dialogue_injection 前缀** — inject 目标 Agent：**完整 L4 知识块 + L6 约束 + 玩家原话**（详见 §6.6）；
2. **scripted_notification** — 本批 L3 活跃但非 inject 目标 Agent：**shared 世界态全文 + 本角色 overlay 摘要**（仍不含玩家原文，Phase 1）。

### 6.4 组装规则（`knowledge.py`）

```python
def build_agent_knowledge(session, agent_id, player_text, *, channel: str) -> str:
    """channel: 'inject' | 'notification'"""
    shared = load_phase_shared(session.phase)
    overlay = load_agent_overlay(agent_id)
    phase_block = overlay.get("phase_overrides", {}).get(session.phase, {})
    turn_block = turn_hints.get(session.player_turn, {})
    glossary = load_glossary_snippet(session.phase)  # 可选

    sections = [
        format_world_state(shared),
        format_atmosphere(shared),
        format_plot_beats(shared),
        format_forbidden(shared),
        format_role(overlay, phase_block),
        format_relationships(overlay, agent_id),
        format_turn_script(turn_block),
        format_glossary(glossary),
    ]
    if channel == "inject":
        sections.append(format_l6_player_directive(player_text))
    return "\n\n".join(s for s in sections if s)
```

### 6.5 知识库 YAML 字段规范（必须详述）

每个 `shared/phase_N.yaml` **至少**包含：

```yaml
phase: "Phase 1"
world_state: |
  （200字+）逐条写清：玩家 place_id、各 Agent 所在 place_id、
  谈判室正在发生什么、前台接待的任务、Sam 状态（冻结/远程）…
scene_atmosphere: |
  （80字+）火药味/紧迫感/前台_busy 等感官与情绪基调。
plot_beats: |
  （100字+）本 Phase 剧情要点，引用 dev_docs/1 与 dev_logs/19。
forbidden_actions: |
  （80字+）禁止 MOVE、禁止 GRP、禁止替 Jensen 做决定…
session_facts: |
  （动态占位，Flask 注入）当前 player_turn、stats 摘要、距节点 A/B/C/D 还有几 Turn。
```

**`session_facts` 注入挂点（定稿）**：在 Flask 侧 `build_turn_context(session, player_text)` 内调用 `knowledge.format_session_facts(session)`，把 `player_turn`、`stats`（Vision/Execution/Trust/Burnout）、距下一节点 Turn 数拼成字符串，写入组装后的 L4 前缀 **【本会话事实】** 段；**不**写进静态 YAML。

每个 `agents/agent_ID.yaml` **至少**包含：

```yaml
identity: |
  姓名、职位、性格关键词、与其他 Agent 关系（100字+）。
speech_style: |
  口语习惯、典型句长（1–3 句）、禁用风格（论文腔/演讲腔）。
player_stance: |
  对玩家的默认态度、如何判断玩家价值、应引用玩家哪些信息。
phase_overrides:
  Phase 1:
    role_goal: |
      （100字+）本 Phase 要完成什么、与谁交互、成功/失败表现。
    example_lines: |
      （2–4 条）符合角色的示例短句，供模仿语气而非照抄。
    response_checklist: |
      - 先回应玩家原话中的 ___ 
      - 再决定是否 RDC/GRP/F2F
```

### 6.6 inject 前缀完整结构（L4 + L6，inject 目标专用）

```text
【系统约束·Phase 2 Turn 7】
（L6：80–120 字 — 角色扮演、先回应玩家、输出 2–4 句、禁止项）

【本 Phase 世界态】（shared.world_state + scene_atmosphere）
…

【本 Phase 剧情要点】（shared.plot_beats）
…

【你的角色与目标】（agent overlay + phase_overrides）
…

【本 Turn 剧本参考】（turn_hints[player_turn]）
…

【关系与术语】（relationships + glossary 可选）
…

【硬性禁止】（shared.forbidden_actions + turn_control 工具矩阵摘要）
…

玩家说：「……」
```

非 inject 的活跃 Agent（如 Phase 1 的 Jensen）通过 **notification** 收到除「玩家说」与 L6 外的 **全部 shared + 角色 phase_overrides**，确保 **上下文同样详细**，但 **不看到玩家原文**（直到前台 RDC 转发）。

### 6.7 超长裁剪优先级（仅兜底）

当组装后超过模型安全阈值（建议单 user 前缀 **≤1500 字** + 玩家原话）时，**从低到高**删除：

1. `glossary` 非本 Turn 术语
2. `example_lines` 保留 1 条
3. `plot_beats` 缩为 bullet 3 条
4. **永不裁剪**：`world_state`、`forbidden_actions`、L6 玩家回应约束、**玩家原话**

### 6.8 Phase 4 Tech VP 旁听 — 知识库示例

`agents/agent_3.yaml` 内 `phase_overrides.Phase 4`：

```yaml
phase_overrides:
  Phase 4:
    role_goal: "你在谈判室角落旁听 Jensen 与玩家的终局对话。"
    speech_style: "本阶段禁止发言、禁止 RDC/GRP/MOVE；仅 do_nothing。"
    silent_observer: true
```

L3 保证 Agent 3 **不 tick**，overlay 仅作文档与未来扩展预留。

---

## 7. 动态温度与输出篇幅（L2）

> **v2.3**：L2 只约束 **模型生成的话**（tool 参数里的 content），**不**限制 §6 注入的上下文长度。

当前 `hbm_scenario.yaml` 已 `temperature: 0.65`，仍偏「话多」。v2.0 **按 Phase 覆盖**（inject 批次内 `temperature_override`）：

| Phase / 场景 | temperature | max_tokens（**输出口语**） | 说明 |
|--------------|-------------|---------------------------|------|
| Phase 1 | **0.45** | **180** | 前台/Jensen **发言** 1–3 句；**输入上下文仍详述** |
| Phase 2 | **0.50** | **220** | 1v1 私密 |
| Phase 3 | **0.62** | **350** | 舌战 **发言** 可略长 |
| Phase 3 Turn 16 | **0.68** | **400** | Sam 搅局 / 广播后略升 |
| Phase 4 | **0.48** | **200** | Jensen **发言** 一句一句 |
| F04 打分 / immediate_msg | 0.3 / 0.8 | — | 不变 |

**overlay 必写**：`speech_style` 中明确「**输入上下文可长，你说出口的内容必须短**」。

**实现**：`f07_agent_control/llm_params.py` → `resolve_llm_params(phase, player_turn)` → 经 `turn_context` 传入 `HbmAgent` 本批 tick。

---

## 8. 玩家中心响应（L6 · v2.0 新增）

### 8.1 inject 文本结构

在 `format_player_dialogue` / `build_inject_payload` 链路上，L4+L6 前缀（**仅 inject 目标 Agent 的 dialogue_injection 事件**）：

```text
【系统约束·Phase 1 Turn 2】
★ 角色扮演：你是{角色名}。下面【世界态】【剧情】【你的目标】描述务必读完再行动。
★ 本拍必须先直接回应玩家下面这句话（复述或引用关键词），再考虑 RDC/其他动作。
★ 你【说出口】的内容：1–3 句口语，禁止演讲腔；上下文详 ≠ 你可以长篇大论。

【本 Phase 世界态】
…（shared，200字+）…

【本 Phase 剧情要点】
…（plot_beats + turn_hint，100字+）…

【你的角色与目标】
…（agent overlay，150字+）…

玩家说：「……」
```

### 8.2 L6 玩家影响链（按 Phase）

| Phase | inject 谁看到玩家原话 | 其他活跃 Agent 如何感知玩家 | 玩家影响路径 |
|-------|----------------------|---------------------------|-------------|
| **1** | `[1]` 前台 | `[2,3]` **不**收玩家原文；仅 shared 世界态 + 前台 RDC 内容 | 玩家→前台 F2F/RDC→Jensen/VP |
| **2** | `[2]` Jensen | `[3]` 仅 Jensen→VP RDC；CEO 被动低频 | 玩家↔Jensen 1v1；Jensen→VP 求证 |
| **3** | `[2–6]` batch 同句 | Sam Turn16+ RDC | 玩家句进全员 memory；NVIDIA 帮玩家 |
| **4** | `[2]` Jensen | `[3]` present_silent 不 tick | 严格 Jensen↔玩家 |

**代码依据**：`HbmAgent._observation_to_text` 把 `player_memory` 置顶为「必须认真回应」；`dialogue_injection` → `update_memory` 是唯一写入路径（`hbm_agent.py`）。故 **非 inject 目标不应收到玩家全文**，否则会 OOC。

### 8.3 Inject 目标 vs Tick 活跃（易混点）

| 概念 | 职责 | Phase 1 示例 | Phase 4 示例 |
|------|------|-------------|-------------|
| **inject 目标**（F05） | 玩家台词写入谁 memory | `[1]` | `[2]` |
| **tick 活跃**（F07 L3） | 本批谁跑 LLM | `[1,2,3]` + CEO 被动 | 仅 `[2]` |
| **旁听**（F07 新态） | 在室但不 tick | — | `[3]` 留 `negotiation_room` |

玩家话**只 inject 给 inject 目标**；其他活跃 Agent 通过 **scripted_notification**（`ScriptEngine.notify_agent` → `obs.scripted_notification`）收 shared 世界态，**不含玩家原文**（Phase 1）。

### 8.4 行为验收

- Phase 1–2：`public_messages` 回复 **含玩家关键词或明确追问**；
- Phase 3：Jensen/VP 回复 **引用** 玩家 batch inject 中的概念；
- Phase 4：每轮 **仅 1 条** Jensen F2F，与上一轮玩家句相关；**无 VP 任何通道消息**。

---

## 9. Turn 控制矩阵（`turn_control.yaml` 真相源）

### 9.1 L3 — 活跃 Agent

| Phase | primary_active | passive / 低频 | present_silent | frozen |
|-------|----------------|----------------|----------------|--------|
| 1 | `[1,2,3]` | `[4,5,6]` 被动 | — | `[7]` |
| 2 | `[2]` | `[3]` 被动 RDC；`[4,5,6]` 更低频 | — | `[1,7]` |
| 3 | `[2,3,4,5,6]` | — | — | `[1]` |
| 3 Turn≥16 | + `[7]` RDC only | — | — | `[1]` |
| 4 | `[2]` | — | **`[3]` 留室不 tick** | `[1,4,5,6,7]` |

**被动 tick 触发**（`pick_active.py`）：
- Agent ∈ `passive_low_freq` 且本 tick 有 **未读入站消息**（F2F 同室 / RDC）→ 加入活跃集；
- Phase 2 Agent 3：额外要求 **sender=2**（仅回复 Jensen RDC，§13.3）；
- `passive_max_per_batch: 1` — 每批 inject 最多 1 次被动 tick，防止 CEO 刷屏。

### 9.2 L5 — 工具白名单（摘要）

| Phase | Agent | 允许 | 禁止 |
|-------|-------|------|------|
| 1 | 1 | `speak_to_local`, `send_message`, `do_nothing`, `update_state` | MOVE, GRP, relation_change |
| 1 | 2,3 | `send_message`, `do_nothing`, `update_state` | MOVE, GRP, speak_to_local（不在前台） |
| 1 | 4–6 | `speak_to_local`, `do_nothing`（被动 tick） | MOVE, GRP, RDC 给玩家 |
| 1–2 | 7 | `do_nothing` only | 全部 |
| 2 | 2 | `speak_to_local`, `send_message`, `do_nothing`, `update_state` | MOVE, GRP |
| 2 | 3 | `send_message`(→2), `do_nothing` | MOVE, GRP, speak_to_local |
| 3 | 2–6 | 全工具（MOVE 仍受节点约束） | — |
| 3 | 7 (T≥16) | `send_message`, `do_nothing` | MOVE, GRP |
| 4 | 2 | `speak_to_local`, `do_nothing`, `update_state` | 其余 |
| 4 | 3 | **（不 tick）** | 全部 — 旁听位 |

### 9.3 MOVE 硬规则

| 规则 | 动作 |
|------|------|
| Phase 1–2 **任意 Agent** | 拒绝 **所有** `request_move` |
| Agent 7, Turn &lt;16 | 拒绝 MOVE |
| Agent 1 | 永久拒绝 MOVE |
| **允许 MOVE 的唯一路径** | F05 `routing.apply_routing` 节点 A/B/C 的 IPC `MOVE_AGENT` |

### 9.4 `turn_control.yaml` MVP Schema（真相源样例）

> 完整矩阵见 §9.1–§9.2；以下为 F07-A 首版可直接落地的 YAML 骨架。

```yaml
enabled: true

# L3 — 活跃 Agent（与 §9.1 表一致）
phases:
  Phase 1:
    primary_active: [1, 2, 3]
    passive_low_freq: [4, 5, 6]
    present_silent: []
    frozen: [7]
    passive_max_per_batch: 1
    passive_tick_probability: medium   # Phase 1 CEO 被动：有未读消息时按概率入队
  Phase 2:
    primary_active: [2]
    passive_rdc_reply: [3]             # 仅 sender=2 的未读 RDC 时 tick
    passive_low_freq: [4, 5, 6]
    frozen: [1, 7]
    passive_max_per_batch: 1
    passive_tick_probability: low      # Phase 2 CEO 被动频率更低
  Phase 3:
    primary_active: [2, 3, 4, 5, 6]
    frozen: [1]
    sam_rdc_from_turn: 16              # Turn≥16 时 [7] 仅 RDC
  Phase 4:
    primary_active: [2]
    present_silent: [3]                # 留室不 tick、不 inject
    frozen: [1, 4, 5, 6, 7]

# L5 — 工具白名单引用（详细规则见 §9.2；实现时展开为 agent×phase 矩阵）
tool_policy: features/f07_agent_control/tool_matrix.yaml

# L2 — 动态温度 / max_tokens（§7）
llm_params:
  Phase 1: { temperature: 0.45, max_tokens: 180 }
  Phase 2: { temperature: 0.50, max_tokens: 220 }
  Phase 3: { temperature: 0.62, max_tokens: 350 }
  Phase 3_turn16: { temperature: 0.68, max_tokens: 400 }
  Phase 4: { temperature: 0.48, max_tokens: 200 }
```

**`passive_tick_probability`**：`low` ≈ 25% 入队概率、`medium` ≈ 50%、`high` ≈ 75%（仅在有未读入站消息且未超 `passive_max_per_batch` 时掷骰）。

---

## 10. 与现有 Feature 的集成

| Feature | F07 集成点 |
|---------|------------|
| **F02** | `handle_player_turn` / `async_inject`：调用 `build_turn_context`，inject payload 带 `turn_context` |
| **F05** | Phase 4 inject 改 `[2]`；节点 C **保持**仅 MOVE CEO 4/5/6；`build_inject_payload` 调用 F07 约束前缀 |
| **F03** | §13.2 Phase 1 F2F 优先；**§13.5 Phase 4 仅 Jensen F2F 完成** |
| **F11** | 无改动的 delta 契约；F07 让 delta 内容「更像剧情」 |
| **F00** | `world_step._pick_active`、`hbm_agent` tool 过滤 |

**数据流**：

```text
player-turn → F07 build_turn_context(session, player_text)
           → F05 build_inject_payload + constraint_prefix
           → F11 async inject { events, turn_context, llm_params }
           → Runner: set_tick_context → N×run_one_tick → clear
```

---

## 11. 实施路线图（F07-A / B / C / D · 共 **4 个开发步骤 / PR**）

> **步骤总览**：F07-A（prompt/知识库/Runner 观测债）→ F07-B（L3/L5 治本 + F03 Phase 1）→ F07-C（Phase 2–3 剧情）→ F07-D（Phase 4 + 全量回归）。每步可独立 review、可回滚（`enabled: false`）。

### F07-A — 快速见效（L1/L2/L4/L6 骨架）

| 项 | 内容 |
|----|------|
| A1 | `turn_control.yaml` + `enabled` 开关 |
| A2 | `story_knowledge/` 混合库 **Phase 1–4 详述首版**（§6.5 字段齐全） |
| A3 | `turn_context.py` + inject **完整 L4+L6 前缀**（§6.6） |
| A4 | `llm_params.py` 读 §9.4 温度表 → **`build_turn_context` 输出 `llm_params` 字段**（Flask 侧；Runner 批内 override 留 F07-B B2） |
| A5 | yaml soul：**保留性格细节**；重复阶段规则 **下沉 L4**；补「阶段服从 + **输入详/输出短**」 |
| A6 | **§19.2** 每 Turn  scoped `player_memory` |
| A7 | **§19.3** Hbm 专用 user prompt 尾（有 player_memory 时替换 Demo 10 条） |
| A8 | **§19.4** stale 守卫跳过 |
| A9 | **§12.3** 撤销 M7 对 F07 的「禁止存在」断言；更新 F05 inject 测试（允许「系统约束」前缀） |

**验收**：Phase 1 Turn 1 GRP=0；中屏 F2F≥1；**F2F 短但含玩家关键词**；inspect inject 前缀 **≥800 字**（含世界态/剧情/角色目标）。

### F07-B — 治本（L3/L5）

| 项 | 内容 |
|----|------|
| B1 | `pick_active.py` + `HbmWorldStep._pick_active` |
| B2 | IPC inject 传 `turn_context` + **Runner 批内 `temperature`/`max_tokens` override**（读 A4 的 `llm_params`；挂点 §19.5） |
| B3 | `tool_guard.py` MOVE/工具拦截（挂点：`hbm_agent.perform_action_by_llm` tool_calls 解析后） |
| B4 | Phase 1 `[1,2,3]` + CEO 被动低频 |
| B5 | F03 Phase 1 F2F 完成语义（§13.2） |

**验收**：Runner 日志 Phase 1 无 Agent 7；无自主 MOVE；Sam 不在前台。

### F07-C — 剧情打磨（Phase 2–3 + 节点）

| 项 | 内容 |
|----|------|
| C1 | Phase 2 Tech VP 被动 RDC（§13.3） |
| C2 | Phase 3 帮玩家 prompt + Turn 16 温度覆盖 |
| C3 | dev_logs/19 → **turn_hints 全 Phase 详述**（每 Turn 80–200 字） |
| C4 | 节点 B/C 回归 |

### F07-D — Phase 4 专规 + 回归

| 项 | 内容 |
|----|------|
| D1 | Phase 4 inject `[2]`；VP **留室旁听**（L3 present_silent）；节点 C 不 MOVE Agent 3 |
| D2 | 1v1 交互验收 Turn 21–25；断言无 Agent 3 消息 |
| D3 | `test_m0_acceptance.py` 扩展 F07 断言 |
| D4 | F03 Phase 4 完成语义（§13.5） |
| D5 | 同步 [`dev_docs/1_story_prototype.md`](../dev_docs/1_story_prototype.md) Phase 4 inject 速查表 → **Agent 2 only**；加注 VP `present_silent` |

---

## 12. 测试与回归

### 12.1 自动化

```text
Phase 1: GRP==0, public_messages>=1, 无 agent7 location 变化
Phase 2: Jensen RDC→3 后出现 Tech VP 被动 tick
Phase 4: 仅 agent 2 有 LLM 请求；无 agent 3 任何消息；agent 3 仍在 negotiation_room
```

### 12.2 人工（必做）

| 阶段 | 检查点 |
|------|--------|
| Phase 1 | 前台短句回应；有价值则 RDC 简报；Jensen/Tech VP 在 Observer 有互动；**无 MOVE** |
| Phase 2 | Jensen 先回应玩家再 RDC；玩梗也能推进；Tech VP 偶尔回 Jensen |
| Phase 3 | NVIDIA 帮玩家；CEO 攻击玩家；Turn 16 Sam 搅局 |
| Phase 4 | 仅 Jensen 与玩家对话；**Tech VP 在室但不发言**；CEO 不在谈判室 |
| Turn 4/12/16/25 | 四节点不退化 |

### 12.3 测试迁移（F07-A 必做 · 相对 M7 清理）

M7 曾移除 F07 运行时并写入**反向断言**；F07-A 落地时需**正向改写**，避免 CI 与实现冲突：

| 现有测试 | 现状 | F07-A 改法 |
|----------|------|-----------|
| `test_m7_legacy_cleanup` | 断言 `features/f07_agent_control/` **不存在** | 改为断言目录 **存在** 且含 `turn_control.yaml` |
| 同上 | 断言根目录 `turn_control.yaml` **不存在** | 删除该断言（yaml 在 feature 子目录） |
| `test_f05_routing_payload` | Phase 1 inject **不得**含「系统约束」 | F07 `enabled: true` 时 **必须**含「系统约束」；`enabled: false` 时保持旧行为 |

§12.1 自动化补充：`inject_prefix` — Phase 1 event text 含「系统约束」且长度 ≥800（F07-A 验收）。

---

## 13. 保留项（v1.1 §13 仍然有效）

### 13.1 Phase 1 中屏 F2F 策略 — **保留选项 A**

必须先 `speak_to_local` 回应玩家，再 RDC。

### 13.2 F03 完成语义 — Phase 1（v2.4 伪代码）

Phase 1 优先 **玩家地点 F2F**；避免 Observer 有 RDC、中屏仍空就 completed。

```python
# completion.py — check_action_complete 内，F07 enabled 且 phase=="Phase 1" 时：
RECEPTION = "nvidia_reception"

if task.phase == "Phase 1":
    if db.has_f2f_after(RECEPTION, start, current_tick):
        return True
    # 不因 Phase 1 RDC(1→2) 或 GRP 提前 completed
    if task.inject_status == INJECT_STATUS_FAILED:
        return True
    if not _inject_finished(task):
        return current_tick >= start + 8
    return current_tick >= start + 8

# Phase 2/3：保持现有 F2F | RDC | GRP 逻辑（Phase 3 不变）
# Phase 4：见 §13.5
```

**代码影响**：Phase 1 分支在 RDC/GRP 检查**之前**短路；`PHASE_RDC_PAIRS["Phase 1"]` 仍保留供 Observer 展示，**不参与** completed。

### 13.3 Phase 2 Tech VP 被动 RDC — **保留**

节点 B 触发依赖 Tech VP 回复。Phase 2 **主活跃仅 `[2]`**；Agent 3 仅在 Jensen→VP 未读 RDC 时被动 tick。

### 13.4 分层有效性 — **增补 L6**

| 层级 | 抑制抢戏 | 玩家交互感 | 篇幅控制 |
|------|----------|------------|----------|
| L3 | ★★★★★ | ★★★☆☆ | ★★☆☆☆ |
| L5 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ |
| L6 | ★★☆☆☆ | ★★★★★ | ★★★★☆ |
| L4 知识库 | ★★★☆☆ | ★★★★★ | ★★★☆☆ |
| L4 **详述（v2.3）** | ★★★★☆ | ★★★★★ | ★★★☆☆ |
| L2 温度 | ★★☆☆☆ | ★★☆☆☆ | ★★★★★ |

### 13.5 F03 完成语义 — Phase 4 增补（v2.1）

| Phase | 完成条件优先级 |
|-------|----------------|
| **Phase 4** | ① `negotiation_room` 有 **Jensen F2F** → completed；② 不因 VP RDC 或 GRP 提前 completed；③ 超时兜底 `start_tick+8` |

**代码影响**：`PHASE_RDC_PAIRS["Phase 4"]` 在 F07 启用时应 **停用或置空**，避免 VP 旁听位触发 completed。

---

## 14. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 约束过严全员沉默 | L3 主活跃列表保证 1–3 人 tick；L6 只要求「先回应」不禁止后续 RDC |
| Phase 1 Jensen 抢前台中屏 | Jensen 无 `speak_to_local` 在前台地点；中屏仍 filter `place_id` |
| Phase 4 VP 误发言 | L3 present_silent + inject 仅 `[2]` + F03 不用 VP RDC 完成 |
| 节点 B 不触发 | §13.3 被动 tick |
| F11 async 丢 turn_context | `async_inject` payload **必须**含 `turn_context`；验收断言 IPC 日志 |
| 与 F11 冲突 | turn_context 随 inject 进 async 路径；不改 F11 delta 契约 |
| 回滚 | `turn_control.enabled: false` 或 revert F07 PR |

---

## 15. 涉及文件一览

| 文件 | 变更 |
|------|------|
| `features/f07_agent_control/**` | **新建** |
| `features/f05_story_routing/routing.py` | Phase 4 inject 改 `[2]`（不改动 node C） |
| `features/f02_player_turn/handler.py` | 调用 F07 turn_context |
| `features/f11_live_turn_sync/async_inject.py` | payload 带 turn_context |
| `core/runner/world_step.py` | pick_active |
| `core/runner/hbm_agent.py` | tool_guard + llm override + **L6 prompt 尾 + stale 守卫** + player_memory  scoped |
| `core/runner/ipc_handlers.py` | set/clear tick_context |
| `hbm_scenario.yaml` | soul 保留性格细节、阶段规则下沉 L4、默认温度 |
| `features/f03_action_result/completion.py` | Phase 1 + Phase 4 F2F 优先 |
| `scripts/test_m0_acceptance.py` | F07 断言 |
| `features/__init__.py` | 注册 F07 |

**不修改**：`agent_world/world/` 引擎核心、`agent_world/demo/`。

---

## 16. 方案命名与状态

| 项 | 值 |
|----|-----|
| 方案代号 | **ABCS**（Agent Behavior Control Stack） |
| Feature ID | **F07** |
| 文档版本 | **v2.4** · 2026-05-25 |
| 开发步骤 | **4 PR**：F07-A → B → C → D（§11） |
| 分支 | `feature/f07-agent-behavior-control` |
| 前置 | F11 ✅ 已合并 |
| 下一步 | **F07-A** 首 PR |

---

## 17. 实施记录

### 17.1 M5 首次实现（2026-05-24 · 已回滚）

曾落地 Phase A–C，M7 清理中移除运行时；设计保留。

### 17.2 v1.1（2026-05-24）

§13 补全 F2F/F03/被动 tick；待 F11 后重建。

### 17.3 v2.0（2026-05-25）

- 整合产品需求：玩家中心、分 Phase 行为、混合知识库、动态温度；
- 确认 **F07 Feature** 形态与 **F07-A/B/C/D** 切分；
- F11 已合并；开发分支已创建。

### 17.4 v2.1（2026-05-25）

- **知识库**：混合模式**定稿**（§6），补充组装规则与 token 预算；
- **Phase 4**：Tech VP **留室旁听不发言**（`present_silent`）；与 `dev_docs/1` 及现有 `node_c` 对齐；
- **修补**：Phase 2 主/被动 tick 分离；inject vs tick 双通道说明；F03 Phase 4 完成语义；被动 tick 上限；
- **删除错误项**：v2.0 误写「节点 C MOVE Agent 3」— 与代码不符，已纠正。

### 17.5 v2.2（2026-05-25）

- 对照 `agent_world` / `hbm_demo` **代码锚点**增补 §19；
- 明确 **玩家影响链**（§8.2）：inject 目标 vs notification 双通道；
- 识别 **Demo 通用 prompt / stale guard / player_memory 累积** 三类与「玩家中心」冲突的实现债；
- F07-A 增加 A6–A8 必做项。

### 17.6 v2.3（2026-05-25）

- **输入详述 / 输出短句** 双轨原则（§3.1）；
- 知识库预算从「≤300 字」调整为 **800–1200 字 inject / 400–700 字 notification**（§6.3）；
- 新增 YAML 字段规范（§6.5）、inject 完整结构（§6.6）、裁剪优先级（§6.7）；
- turn_hints 由「1–2 句」改为 **每 Turn 80–200 字剧本片段**。

### 17.7 v2.4（2026-05-25 · 当前）

- §4 Phase 2 与 §9.1 矩阵对齐（primary `[2]` / passive `[3]`）；
- 新增 **`turn_control.yaml` MVP schema**（§9.4）与 `passive_tick_probability` 定义；
- §13.2 补 **Phase 1 F03 完成伪代码**；
- §12.3 **测试迁移**（M7 反向断言 → F07 正向断言）；F07-A 增 A9；
- 明确 **`session_facts` 挂点**（§6.5）、**L2 A4/B2 分工**、**scripted_notification 调用时机**（§19.7）；
- F07-D 增 D5：同步 `dev_docs/1` Phase 4 inject 表。

---

## 18. v2.1 方案审查清单（自检）

| # | 审查项 | 结论 | 处置 |
|---|--------|------|------|
| 1 | 与 `dev_docs/1` Phase 4「三人留室」一致 | ✅ | VP present_silent，不 tick |
| 2 | 与现有 `node_c` 仅 MOVE CEO 一致 | ✅ | 删除「MOVE Agent 3」误写 |
| 3 | 与 F11 async inject 路径兼容 | ✅ | turn_context 写入 async payload |
| 4 | Phase 1 inject `[1]` vs tick `[1,2,3]` 不矛盾 | ✅ | §8.3 双通道说明 |
| 5 | 节点 B Tech VP 被动 tick | ✅ | Phase 2 primary=`[2]`，passive=`[3]` |
| 6 | Bad End Turn 4 | ✅ | §5.1 硬条件保留 |
| 7 | F03 Phase 4 不因 VP RDC completed | ⚠️ 待实现 | §13.5 |
| 8 | `PHASE_INJECT_AGENTS` Phase 4 改 `[2]` | ⚠️ 待实现 | F07-D |
| 9 | 被动 CEO 刷屏 | ✅ | `passive_max_per_batch: 1` |
| 10 | 知识库过长撑爆 context | ✅ | §6.7 裁剪兜底（详述优先，非极简） |
| 11 | player_memory 跨 Turn 累积 | ⚠️ 待实现 | §19.2 A6 |
| 12 | Demo prompt 与玩家句抢注意力 | ⚠️ 待实现 | §19.3 A7 |
| 13 | stale 强制 update_state 盖过 F2F | ⚠️ 待实现 | §19.4 A8 |
| 14 | Phase 1 F03 可被 RDC  alone 完成 | ⚠️ 待实现 | §13.2 |
| 15 | `scheduler=None` 全 Agent tick | ⚠️ F07-B | L3 唯一解 |
| 16 | 知识库/inject 上下文过简 | ✅ v2.3 | §6.3–§6.7、§3.1 |
| 17 | soul 与 L4 分工 | ✅ v2.3 | L1 性格留 yaml，阶段细则在 story_knowledge |
| 18 | M7 测试与 F07 实现冲突 | ✅ v2.4 | §12.3、F07-A A9 |
| 19 | `turn_control.yaml` 无 schema | ✅ v2.4 | §9.4 |
| 20 | Phase 1 F03 无伪代码 | ✅ v2.4 | §13.2 |
| 21 | `dev_docs/1` Phase 4 inject 过时 | ⚠️ F07-D | §11 D5 |

---

## 19. 代码锚点审查（v2.2 · 对照仓库现状）

> 以下基于 `agent_world/hbm_demo` 与 `agent_world/world` 当前实现；F07 必须在这些挂点落地，否则方案仅停留在 prompt 层。

### 19.1 玩家台词如何进入 Agent（现有链路）

```text
F05 build_inject_payload(session, player_text)
  → dialogue_injection effect（routing.py format_player_dialogue）
  → Runner handle_inject_script_event：ScriptEngine 注册 event
  → 每 tick Phase A：due_events → DialogueInjectionEffect.apply
  → HbmAgent.update_memory → player_memory[]
  → perform_action_by_llm：_observation_to_text 置顶「必须认真回应」
```

**PHASE_INJECT_AGENTS**（`routing.py`）：Phase 1→`[1]`，2→`[2]`，3→`[2–6]`，4→`[2,3]`（F07-D 改为 `[2]`）。

### 19.2 player_memory 应按 Turn  scoped（v2.2 必做）

**现状**：`player_memory` 仅在 `world_reset` 时 `clear()`（`world_reset.py`），25 Turn 内**累积**所有历史玩家句。

**后果**：LLM 同时看到 Turn 1 与 Turn 20 的玩家话，**削弱当前 Turn 因果**。

**F07 规格**：
- 在 **`ipc_handlers.handle_inject_script_event` 批开始前**（或 F07 hook）：对 **本 Phase inject 目标 Agent** 执行 `player_memory.clear()`，再应用本 Turn dialogue_injection；
- 可选：上一 Turn 一句摘要写入 `current_state`（非 MVP）。

### 19.3 Hbm 专用观测 prompt 尾（v2.2 必做）

**现状**：`HbmAgent` 继承 `DemoAgent._observation_to_text`，含 **10 条「必须推进剧情」** 规则 + 全工具列表（`demo_agent.py` ~514–547 行），篇幅远大于 `player_memory` 块。

**F07 规格**：
- 在 `HbmAgent._observation_to_text` 中：若 `self.player_memory` 非空，**替换**尾部 Demo 规则为 **L6 短规则**（先回应玩家、短句、禁 MOVE/GRP）；
- Phase 1 前台：额外强调「speak_to_local 优先于 send_message」。

### 19.4 stale update_state 守卫与玩家 F2F 冲突（v2.2 必做）

**现状**：`DemoAgent._observation_to_text` 在 `stale_ticks >= 5` 时插入「**本拍必须且只能 update_state**」（`demo_agent.py` 337–345 行）。

**后果**：世界 tick 累计后，inject 批次内后期 tick Agent 可能**无法对玩家 F2F**，与 L6 直接冲突。

**F07 规格**：
- 若本 Turn 有 **新写入的** `player_memory`（或 `turn_context.player_turn` 匹配），**跳过** `force_update_state` 块；
- 或在每批 inject 开始时 `current_state_set_at = world.t`（inject 目标 Agent）。

### 19.5 LLM 参数批内覆盖（F07-B）

**现状**：`kernel.build_kernel` 创建 Agent 时固定 `temperature` / `max_tokens`（`kernel.py` 345–346）；`perform_action_by_llm` 读 `self.temperature`。

**F07 规格**：
- `HbmWorldStep` 持有 `tick_context`；`_run_single_agent` 前设置 `agent._batch_temperature` / `_batch_max_tokens`；
- `perform_action_by_llm` 优先读 batch  override，批末清除。

### 19.6 Tick 活跃与工具 dispatch（F07-B）

**现状**：`WorldStep._pick_active`：`scheduler=None` → **全部 Agent**（`world/step.py` 228–236）；`HbmWorldStep` 同地点并行 LLM。

**F07 规格**：`HbmWorldStep._pick_active` 委托 `f07.pick_active.pick_active_ids(turn_context, world, t)`。

**工具**：`perform_action_by_llm` 解析 tool_calls 后 → `tool_guard.filter_tool_calls(agent_id, turn_context, calls)` → 非法改为 `do_nothing`。

### 19.7 scripted_notification（非 inject 活跃 Agent）

**现状**：`PerceptionBuilder` 读取 `script_engine.pending_for(agent_id)` → `obs.scripted_notification`；`HbmAgent` 会渲染进 user prompt。

**F07 规格**：inject 批开始时，F07 对 **本批 L3 活跃但非 inject 目标** 的 Agent 调用 `script_engine.notify_agent(id, shared_phase_snippet)`，**不含玩家原文**。

**调用时机（定稿）**：

```text
Runner handle_inject_script_event(payload):
  1. 解析 payload.turn_context（F07-B 起）
  2. world_step.set_tick_context(turn_context)     # 含 llm_params
  3. ★ F07：对 active_non_inject agents → notify_agent(snippet)   # 在 events 注册之后、tick 循环之前
  4. ScriptLoader.load_dict(events) → script_engine
  5. ★ F07-A6：scoped clear player_memory（inject 目标）
  6. for _ in range(tick_loops): run_one_tick()
  7. world_step.clear_tick_context()
```

Flask 侧 **不**调用 `notify_agent`（无 ScriptEngine）；notification 仅在 Runner inject 批内生效。

### 19.8 F03 完成判定（待 F07 改）

**现状**（`completion.py` 55–62 行）：任意 F2F **或** 阶段 RDC 对 **或** GRP 即 `completed`；**无 Phase 区分**。

**与产品目标冲突**：Phase 1 可能 Observer 有 RDC、中屏无 F2F 仍结束 Loading。

**F07**：实现 §13.2 / §13.5；且 `inject_status != done` 时 F11 已有守卫（F03 + F11-A）。

### 19.9 方案有效性判断（v2.2 结论）

| 问题 | 仅靠 prompt | + L3/L5 | + L6/A6–A8 | 预期 |
|------|------------|---------|------------|------|
| CEO/Sam 抢戏 | ❌ | ✅ | ✅ | 可解决 |
| 乱 MOVE | ❌ | ✅ | ✅ | 可解决 |
| 玩家句被忽略 | ⚠️ | ⚠️ | ✅ | **需 A7+A6** |
| 回复太长 | ⚠️ | ⚠️ | ✅+L2 | 输出口语仍受 max_tokens 约束 |
| 上下文不足导致 OOC | ⚠️ | ⚠️ | ✅+§6 详述 | **v2.3 补强** |
| 中屏 completed 无 F2F | ❌ | ❌ | ✅+§13.2 | 需 F03 改 |

**结论**：v2.3 方案在 **F07-A（详述知识库 + A6–A8）+ F07-B + F03** 落地后，可同时达成 **上下文充分、角色代入、玩家中心** 与 **口语短句输出**。

---

*本文档为 Agent 行为控制（F07 ABCS）的**唯一设计依据**；实施以 §5 Phase 规格 + §9 矩阵 + §11 路线图 + **§19 代码挂点** 为 PR 边界。剧情数值路由以 [`dev_docs/1_story_prototype.md`](../dev_docs/1_story_prototype.md) 为准，行为矩阵以本文为准。*
