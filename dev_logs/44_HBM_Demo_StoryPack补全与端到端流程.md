# HBM Demo Story Pack 补全清单 + 端到端流程说明

> 由多智能体工作流(四维完备性审查 + 综合)生成。配套 dev_logs/40/41/42/43。
> 第一部分=Story Pack 补全清单(已并入 dev_logs/42 §9);第二部分=端到端流程说明。


> 配套 dev_logs/40（耦合点清单）、41（AI4VisualNovel 借鉴）、42（数据驱动化完整规划）、43（管理者 vs 演员 agent）。本文基于四维完备性审查（World Primitives / Agent Side / 游戏元呈现 / Story Pack 机制）收口，目标判据不变：**只改 `config/stories/<id>/` 就能换一个完全不同的游戏，前后端代码零 diff**。

---

## 第一部分：dev_logs/42 补全清单

dev_logs/42 已规划 11 个 Story Pack 文件（`meta / story_graph / places / agents / groups / signals / endings / judges / timed_events / language_style / ui_text` + `prompts/` + `assets/`），但四维审查发现：**世界原语层的 relations / capabilities / coverage / place_mutation / seed 初始世界状态 / memory / perception 这一整排「引擎读 scenario」的配置，在 42 的 Story Pack 文件清单里没有显式落点**。本节把所有 `covered_by_plan = partial / no` 的要素整理成"需要补进 Story Pack"的清单，每条给出：要素 → 现在在哪 → 补到哪个文件/字段（或注明"引擎已通用无需配置"）。

### A. 世界原语层（引擎 / world.db）—— 42 漏配的主体

| 要素 | 现在在哪 | 补到 Story Pack 哪个文件 / 字段 |
| --- | --- | --- |
| **关系网 relations（最关键遗漏）** | `hbm_scenario.yaml` L80-89 `relations:`（src/dst/type/symmetric）；`kernel.seed_world()` → `RelationGraph.add()` | **新增 `config/stories/<id>/relations.yaml`**：`relations: [{src_role, dst_role, type, symmetric, metadata?}]`。src/dst 用 `agents.roles` 解引用而非裸 id；type 受 conscribe 注册的 `relation_types` 白名单约束；symmetric 时生成互向边。seed 期 `seed_world()` 改读此文件而非 scenario。**运行期实时变化（如 Samsung 背刺）仍由通用 `relation_change` 工具驱动，无需故事特定配置——引擎已通用。**（也可作为 `relations:` 块并入 `agents.yaml`，但独立文件更清晰，推荐独立。） |
| **能力授予 capabilities** | `hbm_scenario.yaml` L71-78（agent_id/capability）；`seed_world()` → `CapabilityTable.grant()` | **`agents.yaml` 每个 agent 加 `capabilities: [signal_uplink, ...]` 字段**（推荐，按角色就近）；或独立 `capabilities.yaml: [{agent_role, capability, granted_at, metadata?}]`。seed 期从此读，控制"换故事时哪些 agent 能调 story_advance"。**运行期动态授予/撤销**：在 `timed_events.yaml` 或 `story_graph` 边的 actions 中新增 `capability_grant / capability_revoke` action。 |
| **连通性 coverage** | `hbm_scenario.yaml` L57-69（src/dst/latency_ticks）；`ConnectivityResolver` | **并入 `places.yaml`**：`coverage: [{src_place, dst_place, latency_ticks, can_reach}]`，src/dst 用 places 解引用。42 已规划 places.yaml，此处补齐 coverage 子段即可（已 partial→明确归位）。 |
| **地点变异 place_mutation** | `hbm_scenario.yaml` `places[].attrs.behavior_hint` 初值；`routing.py` L49 `NODE_B_BEHAVIOR_HINT` 硬写；`world_db.update_place_attrs()` | **新增 `config/stories/<id>/place_behaviors.yaml`**：`places: {place_id: {initial_behavior_hint, mutations: [{label, text}]}}`。seed 期用 `initial_behavior_hint` 填 `place.attrs`；`story_graph` 边的 `place_mutations` 改为引用 `mutations[].label`（而非内联文本）；`timed_events` 也支持 `place_mutation` action，补齐非节点转移触发的变化。 |
| **seed / 初始世界状态（agent soul/goal/state）** | `hbm_scenario.yaml` L109-221 `agents[].soul/long_term_goal/current_state`；散落在 `prompts/story_knowledge/agents/agent_*.yaml` | **扩展 `agents.yaml` schema**：`{id, name, role, faction, init_place, capabilities, soul_template, long_term_goal, initial_state, overlay}`。把 soul/goal/state 从 scenario 收口到 `agents.yaml`（或 `prompts/agent_*.yaml`），换故事时随包替换。 |
| **初始记忆 initial_memories（seed 期 memory）** | 无 seed 机制。`SegmentStore(world_db)` 由引擎自动跑，无初始记忆注入接口 | **新增 `config/stories/<id>/memory.yaml`** 的 `initial_memories: {agent_role: [{created_at, content, importance_score, tags}]}`；或在 `prompts/agent_*.yaml` overlay 加 `initial_memory` 字段（t=-1 段）。需补一个 **`SegmentStore` seed 接口**（`memory/updater.py` 或 `MemoryEngine` 层），`seed_world()` / `world_reset` 后回放。 |
| **memory 压缩 / 健忘策略** | `memory/{updater,retrieval,compressor}.py` 行为全部代码写死（窗口、retention、压缩策略），无 config | **`memory.yaml` 的 `segment_compressor: {strategy, window_size_ticks, retention_days}`**。`kernel` 在 `SegmentStore` 初始化后加载并应用；需改 `CompressorPolicy` 接口接收配置。**注意：若所有故事共用同一套通用记忆引擎（团队已确认 memory 是通用引擎自动跑），此块可保持默认、不强制配置——引擎已通用，仅作可选 overlay。** |
| **perception 感知策略** | `world/perception.py` + `memory/perception.py` 写死（F2F/旁听/RDC 优先级、是否感知失败消息） | **新增 `config/stories/<id>/perception.yaml`**（可选）：`agents: [{id, modalities: {F2F, RDC, GRP, overhear}, filters: {place_blacklist, agent_whitelist}}]`。`PerceptionBuilder` 初始化时加载、传入 `perception_build()`，支持 per-agent / per-modality 过滤。**默认全开时引擎已通用，仅当某故事需要"某 agent 不该听到同室对话"才配置。** |
| **群组动态成员变更** | `groups.yaml`（已规划初始成员）；`group_event` 用 `occurred_at=-1` 表"创群"；无加入/退出时间线 | **`timed_events.yaml` 新增 `group_action: {type: add_member|remove_member, group_id, agent_role, at_tick}`**。seed 期按 `groups.yaml` 初始化，运行期按 timed_events 逐项应用。 |
| **clock 时间线** | `hbm_scenario.yaml` L6-8 `clock`；`Clock(t0=0)` | **`meta.yaml` 的 `timeline: {start_time, minutes_per_tick}`**（42 已规划，归位即可，无遗漏）。 |
| place / coverage 基础 / overhear / direct_message(F2F/RDC/GRP) / story_advance_log / agent_llm_trace | 各自 schema + `world_db` + dispatcher/buses | **引擎已通用无需配置**：overhear 是 F2F 衍生（dispatcher 自动插）；channel_type 由 buses 决定，world.db 仅存储；两类 log 是审计自动生成，与故事无关。 |

### B. Agent 侧（人设 / memory / 关系 / 能力 / 工具 / 选角 / 行为卡）

| 要素 | 现在在哪 | 补到 Story Pack 哪个文件 / 字段 |
| --- | --- | --- |
| **Knowledge / memory overlay** | `config/prompts/abcs/story_knowledge/agents/agent_*.yaml`（identity/speech_style/player_stance/relationships/phase_overrides）；`shared/{phase_*, plain_language}.yaml` | **整目录迁入 `config/stories/<id>/prompts/agents/*.yaml`**；`story_knowledge/shared/*` → `config/stories/<id>/language_style.yaml`（含 plain_language）。**改 `knowledge.py` 的 `load_agent_overlay()` / `load_phase_shared()` 为按当前 `story_id` 查 Story Pack 路径**，而非固定 `story_knowledge/` 目录（这是 partial 的核心代码改造点）。 |
| **可用工具白名单 + story_advance 信号 enum** | `hbm_agent.py` L47-78 `STORY_ADVANCE_TOOL`（硬编码 6 个 enum + 中文描述）、L84-92 `_HBM_TOOLS_LIST`；`story_signals.py` L7 `VALID_STORY_SIGNALS` | **`signals.yaml` 的 `valid_signals[]`（已规划）+ 新增 `tools.yaml`**（通用工具描述若需参数化）。`hbm_agent.py` 改为动态构造：`for sig in load_signals().valid_signals: tool["enum"].append(sig.name)`。 |
| **Turn 选角映射 SAM_ID / RECEPTION_AGENT_ID** | `pick_active.py` L28-29 硬编码 `SAM_ID=7 / RECEPTION_AGENT_ID=1`；L42-49 硬编码"Phase3 且 turn≥16 加 Sam" | **`agents.yaml` 的 `roles: {reception:1, leader:2, tech_vp:3, suppliers:[4,5,6], disruptor:7}`**。`pick_active.py` 从 roles 解引用特殊 agent；"turn≥16 激活 disruptor"迁到 `timed_events.yaml` 的 `activate_agents`。 |
| **Agent 行为卡（240+ 行 `_hbm_short_action_rules`）** | `hbm_agent.py` L233-367 `if aid==N and phase=="Phase X"`；`story_knowledge/agents/agent_*.yaml` 的 `phase_overrides`（response_checklist/forbidden_extra） | **`story_graph.yaml` 每个 node 嵌 `agent_behaviors: {agent_id: {respond_rule, length_rule, tool_constraints, keywords_to_watch}}`**（dev_logs/42/43 提到但未给完整 schema，此处补齐）。`hbm_agent.py` 改 `build_agent_prompt(aid, node)` 表驱动模板拼装，删 if 链。`phase_overrides` 按 `node_id` 重组迁入 `prompts/`。 |
| **respond_rule / length_rule / output_hint** | `hbm_agent.py` L305-351；`agent_*.yaml speech_style` | 并入上面 `node.agent_behaviors`；node 级长度约束用 `node.output_hint`（42 已规划 `phases[].output_hint`）。 |
| **记忆注入规则（DialogueInjection：何时/向谁/什么 channel 注入）** | 硬编码在 `f07_agent_control/conversation/control.py` + `pick_active.py` | **可选扩展**：`turn_control.yaml` 或 node 加 `inject_rules: [{node, agents, channel, template}]`。**同构故事不关键（player_memory 引擎通用），异构故事才需要——引擎已通用，仅作可选 overlay。** |
| Agent 人设/soul / 初始位置 / LLM 全局参数 / 禁止项约束 | `scenario.agents[].soul` / `.location`；`hbm_scenario.yaml llm{}`；`shared/phase_*.yaml forbidden_actions` | 已在 `agents.yaml`（soul/init_place）、`meta.yaml`（llm 默认）、`language_style.yaml`（forbidden）覆盖，归位即可。 |

### C. 游戏元 / 呈现（控制流 / 前端 / 素材）

| 要素 | 现在在哪 | 补到 Story Pack 哪个文件 / 字段 |
| --- | --- | --- |
| **节点路由（Phase / 节点 A/B/C/D）** | `routing.py` L155-195 三个 `node_*_applies` if 链；`agent_signals.py` `detect_node_a/b/c`；`story_signals.py VALID_STORY_SIGNALS` | **`story_graph.yaml`（nodes + edges，42 已给完整 schema）** + 新增 `shared/story_graph.py`（StoryGraph 类）+ `features/f05_story_routing/interpreter.py`（TRIGGER_HANDLERS/ACTION_HANDLERS）。routing.py 改表驱动委托 interpreter。 |
| **时序事件（Turn16 广播 / 激活）** | `routing.py` L42-51 常量 + L123-135 `if player_turn==16 and phase=="Phase 3"`；`pick_active.py` L42-49 | **`timed_events.yaml`（42 已规划但代码 0 实现）**：`events: [{turn, node_filter, broadcast, inject, activate_agents, enable_features}]`。`build_inject_payload` 改遍历 timed_events[]。 |
| **结局判定（trust 阈值 if 链）** | `routing.py` L252-281 `if trust>=25 / >=15`；`watcher.py` 写死 `bad_reject`；`f14/handler.py` L80-88 `ending_status_map` | **`endings.yaml` 决策表（已规划）+ `safe_eval`**；`ending_status_map` 移到 `endings[].status`，`f14` 改查表。 |
| **裁判 / 评分（system prompt 写死故事名 + tech_keywords）** | `f04_stats/scoring.py` L43/L66-99；`routing.py` 两段分类 prompt | **`judges.yaml`（已规划）**：`scoring.system_prompt` 模板 `.format(game_title, dimensions_str)` + `dimensions` + `tech_keywords`；三段 LLM prompt 模板化。 |
| **四维属性初值 INITIAL_STATS** | `f01_session/constants.py` L15-20 | **`meta.yaml` 的 `game_config.initial_stats`**。 |
| **玩家实体各 Phase 地点 / F2F 对象** | `f17_virtual_player/player_entity.py` L29-37、`player_f2f.py` L18-23 默认字典 | **`story_graph.yaml` 的 `node.player_place` / `node.player_f2f_recipient`**（已规划）。 |
| **simulation_id / 故事身份 / final_turn** | `hbm_scenario.yaml` L1；`f01_session/constants.py` `DEFAULT_SIM_ID` | **`meta.yaml` 的 `simulation_id` / `game_config.final_turn`**（25→config）。`constants.py` 读 scenario。 |
| **关键词集合（approve/reject/expel/escort/tech_vp_approval…）** | `routing.py` L34-40 tuple；`routing_config.py` | **`signals.yaml` 的 `keyword_sets`（已规划）**；`routing_config` 改从 story_pack 读、无默认值。 |
| **前端 UI 文案（角色名/地点名/群名/幕过渡/结局文案/bad_end）** | 前端 `constants/{agents,groups,places,phaseTransitions}.ts`、`EndingScreen.tsx`、`storyAssets.ts` 全部硬编码 | **`ui_text.yaml`（已规划但下发通道 0 实现）**：后端 session 初始化编译前端可见子集为 JSON，随 `GET /scenario` 或首帧 `world_delta` 下发；前端 `constants/*` 改从 store/context 注入。 |
| **立绘 / 背景素材路径** | `storyAssets.ts` L5-25 硬编码；scenario 无 assets 字段 | **`assets/` 目录 + `meta.yaml.assets` 或 `ui_text.assets`** 路径映射；`storyAssets.ts` 改从 `ui_text.assets` 读。 |
| **Phase 字符串 → node_id** | `session.phase` 遍地读写；`gameStore.ts` 初始 `phase='Phase 1'` | `session.current_node_id` 替代控制流；`phase` 退化为 `story.get_node(current_node_id).beats_label` 只读导出（方案 B）。 |

### D. Story Pack 机制层（换故事的运行时基础设施）—— 当前实现度 0

| 要素 | 现在在哪 | 补到哪 |
| --- | --- | --- |
| **故事选择 STORY_ID** | `DEFAULT_SIM_ID='hbm_memory_war'` 写死；`routes.py` 写死 sim_id | `constants.py` 读 `$STORY_ID` 环境变量（兜底 hbm_memory_war）；`routes.py` session_start/reset 接受 `story_id`；`paths.py get_sim_dir/get_scenario` 按 story_id 返回 `config/stories/<id>/`。 |
| **Story Pack 加载器** | 无 `config/stories/` 目录；仅 `hbm_scenario.yaml` | 新建 `config/stories/hbm_memory_war/`（拆 scenario 为 §A-C 的 YAML 集）；新建 `shared/story_pack.py`（`load_story_pack(story_id)` + `role_to_id/place/faction` 解引用 + `safe_eval`），支持多故事缓存。 |
| **加载期 validate() 门禁** | `seed_world()` 无任何校验，错配运行时 crash | `StoryGraph.validate()`（DFS 无环、root 存在、非 ending 有出边、BFS 结局可达、`edge.rdc_chain ⊆ from_node.allowed_rdc_pairs`、role/place/agent 全量解引用）；`pack.validate()`（role∈roles、faction∈factions、signal/timed_event 的 node 存在、**relations 引用的 agent 在 agents[] 内**、**capabilities 引用的 agent/能力名合法**）。失败 raise `ValidationError` 阻止 seed，`routes.py` 返回 400。 |
| **前端 ui_text 下发通道** | 后端无下发机制 | `routes.py` 新增/扩展 `/scenario` 返回 `ui_text`；前端 `StoryConfigContext` 注入。 |

### 更新后的完整 Story Pack 文件清单

在 dev_logs/42 §3 的 11 个文件基础上 **新增 4 个文件 + 4 处字段扩展**（★ = 42 漏配、本清单新增；☆ = 42 已列但需补字段）：

```
config/stories/<story_id>/
├── meta.yaml              # simulation_id / 故事名 / timeline(start_time,minutes_per_tick)
│                          #   / 初始 node / game_config{final_turn, initial_stats} / 玩家
├── story_graph.yaml       # ★核心 DAG: nodes + edges
│                          # ☆ node 内补 agent_behaviors{aid:{respond_rule,length_rule,
│                          #   tool_constraints,keywords_to_watch}} + player_place/f2f_recipient
├── places.yaml            # 地点表
│                          # ☆ 补 coverage:[{src_place,dst_place,latency_ticks,can_reach}]
├── place_behaviors.yaml   # ★新增：地点 behavior_hint 初值 + mutations 库（place_mutation 解引用）
├── agents.yaml            # 角色表 + roles{} + factions{}
│                          # ☆ 每 agent 补 capabilities[] + soul_template/long_term_goal/initial_state
├── relations.yaml         # ★新增：初始关系网 [{src_role,dst_role,type,symmetric,metadata?}]
│                          #   （运行期 relation_change 由通用引擎驱动，不在此配）
├── groups.yaml            # 群组/阵营显示（动态成员变更走 timed_events.group_action）
├── signals.yaml           # story_advance 白名单 valid_signals + keyword_sets + intent_heuristics
├── tools.yaml             # ★新增（可选）：通用工具描述（若需参数化；否则 enum 从 signals 动态拼）
├── endings.yaml           # 结局决策表 + bad_end（status 字段供 game_over/completed 映射）
├── judges.yaml            # 裁判维度 + tech_keywords + 三段 LLM prompt 模板
├── timed_events.yaml      # ★实现：Turn N 广播/激活/inject + group_action + capability_grant/revoke
├── memory.yaml            # ★新增（可选）：segment_compressor 策略 + initial_memories
│                          #   （引擎默认通用；仅故事需定制健忘度/初始记忆时配）
├── perception.yaml        # ★新增（可选）：per-agent per-modality 过滤
│                          #   （引擎默认全开通用；仅故事需"某 agent 不该听同室"时配）
├── language_style.yaml    # 禁用术语 / 大白话 / plain_language_agents / forbidden_actions
├── ui_text.yaml           # 前端可见子集（agents/groups/places/phase_transitions/endings/init/assets）
├── prompts/               # ★迁入：agent 人设 overlay + knowledge（含 initial_memory 段）
│   ├── agents/agent_*.yaml
│   └── shared/*.yaml
└── assets/                # 背景图 / 头像（路径由 ui_text.assets 映射）
```

**一句话**：42 把"叙事控制流"（story_graph/signals/endings/judges/timed_events）规划完整了，但漏掉了"世界原语播种"这一排——**relations / capabilities / coverage / place_mutation / 初始 memory / perception**。补齐后，世界 DB 的每张表（place/coverage/capability/relation/group/agent_location/segment）都有明确的 Story Pack 配置来源，真正做到"改 config 换世界"。

---

## 第二部分：端到端流程说明（给一套剧情 → 怎么设计游戏 → 后台怎么跑）

### 0. 一图看全：从剧情到一局游戏

```
┌─────────────────────── 设计期（离线，一次性）────────────────────────┐
│  一句话剧情需求                                                       │
│      │                                                                │
│      ▼   生成期管理者（独立 authoring 工具，story_authoring/）         │
│  DesignerAgent ──拆 DAG──▶ ProducerAgent ──分权限/审无环──▶ WriterAgent│
│   (产 nodes/edges)         (产 active/frozen/inject)    (补全元数据)   │
│      │            Plan→Review→Revise 循环到 validate() 通过            │
│      ▼   ※ 也可人工直接手写 YAML（schema 不依赖 LLM）                  │
│  产物 = config/stories/<id>/  （18 个 YAML + prompts/ + assets/）      │
└───────────────────────────────────────────────────────────────────────┘
        │ 数据契约：纯 YAML 文件，authoring 工具永不碰 world_state
        ▼
┌─────────────────────── 启动一局（session start）─────────────────────┐
│  前端 POST /session {story_id}                                        │
│      ▼  L3 Flask routes.py                                            │
│  STORY_ID → load_story_pack(id) → pack.validate() ──失败──▶ 400      │
│      │（无环 / root 存在 / 结局可达 / RDC 对子集 / role·place 解引用） │
│      ▼  L1 Runner kernel.build_kernel() → seed_world()                │
│  播种 world.db：place / coverage / capability / relation /            │
│                 chat_group / agent_location(初始位置) / segment(初始记忆)│
│      ▼  world_loop 起步，current_node_id = root                       │
└───────────────────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────── 运行期每 turn（实时循环）─────────────────────┐
│ ① 玩家输入 ─POST /player_turn─▶ Flask ─IPC─▶ Runner                   │
│ ② world_loop.tick() 推进世界时钟                                      │
│ ③ 选角 pick_active：读 story.get_node(current_node_id).active/frozen  │
│ ④ 演员 agent 并发 LLM 决策（7 路并发）                                │
│     每个 agent 读：人设(soul+overlay) + memory(SegmentStore 检索)      │
│                  + 权限(capability) + 当前 node 行为卡                 │
│     产出：对白 / 移动 / 信号(story_advance) / relation_change          │
│ ⑤ 引擎更新世界：memory 累积、关系变化、agent 移动、消息总线分发        │
│     (F2F 同室广播→overhear；RDC 远程；GRP 群发)                        │
│ ⑥ 确定性解释器 interpreter.apply_routing()：                          │
│     for edge in story.get_edges_from(current_node_id)(按 priority):   │
│        if detect(edge.trigger): apply_actions(edge.actions)           │
│           current_node_id = edge.to                                   │
│     ＋ _process_timed_events（Turn N 广播/激活）                       │
│ ⑦ 裁判点（仅少数）：L2 f08_director.JudgeAgent（LLM 活判断）          │
│     Turn25 意图分类 / Phase4 成交判定 / 四维评分 → 只写 session 变量   │
│ ⑧ 结局决策表 resolve_ending：endings.yaml + safe_eval 选 ending_id    │
│ ⑨ world_delta 经 IPC → Flask → 前端（含 AIGC 实时出图）               │
└───────────────────────────────────────────────────────────────────────┘
```

### 1. 设计期（给一套剧情 → 变成 Story Pack）

起点是**一句话或一份剧情需求**（"一个芯片巨头和供应商在显存定价上的多方谈判，玩家是外来访客，4 幕推进，按信任度分 3 个结局 + 1 个坏结局"）。把它变成可运行游戏，走 dev_logs/43 的**生成期管理者**三角色协作（落在独立离线工具 `agent_world/hbm_demo/story_authoring/`，既不进引擎、也不进 Runner 的 world_loop、更不塞进 Flask 请求周期）：

1. **DesignerAgent（设计官）**：解析需求文本 → 产出 DAG 拓扑，即 `story_graph.yaml` 的 `nodes[]`（节点 = 一幕/一关，带 `beats_label`）+ `edges[]`（from/to/trigger，每条边对应一个推进条件）。这一步把"Phase 1→2→3→4 + 末端分岔到 join/seed/cold/bad_end"画成图。

2. **ProducerAgent（制片人）**：审核 DAG（无环、所有结局可达）+ 为每个节点分配权限——`active_agents / passive_agents / frozen_agents / inject_agents`、`allowed_rdc_pairs`、`player_place`。同时把**世界原语**落地：写 `relations.yaml`（谁与谁结盟/从属/敌对）、`agents.yaml` 的 `capabilities`（谁能调 story_advance）、`places.yaml` 的 `coverage`（地点连通+延迟）。

3. **WriterAgent（编剧）**：整合补全元数据，产出完整 Story Pack——`signals.yaml`（信号白名单 + 关键词集）、`endings.yaml`（结局决策表 + bad_end）、`judges.yaml`（裁判维度 + tech_keywords + LLM prompt 模板）、`timed_events.yaml`（Turn16 AMD 快讯 + Sam 激活）、`language_style.yaml`、`ui_text.yaml`、`prompts/`（agent 人设 overlay + 初始记忆）、`assets/`。

三角色走 **Plan → Review → Revise** 循环，直到 `validate()` 通过才冻结。**关键**：初版可以全部手写 YAML，schema 和解释器逻辑不依赖管理者是不是 LLM——LLM 只是加速器。

**产物 = `config/stories/<id>/`**，一个完全自包含的数据包，通过 YAML 这个唯一数据契约与运行期交互，authoring 工具永不触碰 world_state。

### 2. 启动一局（session start）

1. 前端 `POST /session {story_id}` 到 **L3 Flask**（`routes.py`）。Flask 是薄传输层 + session 管理，不做任何剧情判断。
2. 由 `STORY_ID`（环境变量或请求参数）→ `paths.py` 解析到 `config/stories/<id>/` → `shared/story_pack.py::load_story_pack(id)` 读全部 YAML。
3. **加载期门禁 `pack.validate()`**：StoryGraph 无环（DFS）、root 存在、每个非 ending 节点有出边、所有 ending 可达（BFS）、每条 `edge.rdc_chain` 的 pair ⊆ `from_node.allowed_rdc_pairs`、所有 role/place/agent/relation/capability 引用可解。任一失败 → `raise ValidationError` → Flask 返回 400，**绝不进运行期**。
4. **L1 Runner** `kernel.build_kernel() → seed_world()` 把 Story Pack 播种进 **world.db**：`place`（地点）/ `coverage`（连通性+延迟）/ `capability`（能力授予）/ `relation`（初始关系网）/ `chat_group` + `group_member`（群组）/ `agent_location`（agent 初始位置）/ `segment`（初始记忆，若 `memory.yaml` 配了 `initial_memories`）。agent 的 soul/goal/state 从 `agents.yaml` 装配进 `HbmAgent`。
5. `world_loop` 起步，`session.current_node_id = root_node_id`，`session.phase = root.beats_label`（只读导出）。世界开始运行（剧情模式下世界持续运行，画面尽量跟上）。

### 3. 运行期每个 tick / turn 怎么跑

一个玩家 turn 的完整链路（对应总图 ①-⑨）：

1. **玩家输入**：前端 `POST /player_turn` → Flask → IPC → Runner（所有 LLM 调用都在 Runner 进程内）。
2. **world_loop 推进**：`tick()` 推进世界时钟（纯函数，~1-10ms）。
3. **选角 `pick_active`**：读 `story.get_node(current_node_id)` 的 `active_agents / passive_agents / frozen_agents`，决定本 turn 谁实时表演、谁低频、谁冻结。特殊 agent（reception/disruptor）从 `agents.roles` 解引用，不再硬编码 SAM_ID/RECEPTION_AGENT_ID。
4. **演员 agent 并发 LLM 决策**：被选中的 agent（HBM 是 7 路并发）各自调 LLM。每个 agent 读取：**人设**（`scenario.agents[].soul` + `prompts/agent_*.yaml` overlay）+ **memory**（`SegmentStore` 按当前情境检索，由通用引擎自动压缩/检索）+ **权限**（`CapabilityTable`，能不能调 story_advance）+ **当前 node 行为卡**（`node.agent_behaviors[aid]` 的 respond_rule/length_rule/tool_constraints）。产出：**对白**（speak_to_local / RDC / GRP）、**移动**、**信号**（`story_advance(approve_visitor…)`）、**关系变化**（`relation_change`）。
5. **引擎更新世界**：memory 累积（perception → SegmentStore）、关系实时变化（`relation_change` 工具走通用 `RelationGraph`）、agent 移动（`agent_location`）、消息总线分发（F2F 同室广播衍生 `overhear`；RDC 远程；GRP 群发）。**这一切都是通用引擎自动跑，与具体故事无关。**
6. **确定性解释器 `interpreter.apply_routing()`**（dev_logs/42 的核心，零 if 链）：遍历 `story.get_edges_from(current_node_id)`（按 priority 降序），对每条边 `detect(edge.trigger)`——trigger 经 `TRIGGER_HANDLERS` dispatch（story_signal / rdc_chain / rdc_positive / rdc_expel / reception_reject / phase_timeout / condition）。命中则 `apply_actions(edge.actions)`——经 `ACTION_HANDLERS` dispatch（agent_moves / place_mutations / state_updates / inject / broadcast），然后 `current_node_id = edge.to`，`session.phase = to.beats_label`。同时 `_process_timed_events` 处理 Turn N 事件（Turn16 AMD 广播 + Sam 激活）。**这是纯确定性、可回归、~毫秒级的表驱动推进，不请任何 agent。**
7. **裁判点（仅极少数，dev_logs/43）**：只有"必须读懂自由文本语义、规则写不死"的点才上 **L2 `f08_director.JudgeAgent`**（LLM 活判断），即 Turn25 玩家意图分类 / Phase4 是否真成交 / 四维评分（vision/execution/trust/burnout）。它由 L1 Runner 经 `integration/abcs.py` 白名单受控调用（`director_enabled` 可开关，默认关=100% 确定性），**只往 session 写评分数据，绝不改 agent 权限、不改 edge 转移、不禁言演员**。
8. **结局决策表 `resolve_ending`**：读 `endings.yaml`，按 priority 遍历——先看 `override_signal`（offer_join/offer_seed 强制覆盖），再 `safe_eval(when)`（`intent=='join_nvidia' and trust>=25`），最后 fallback。选出 `ending_id` 及其 `status`（completed/game_over）。
9. **`world_delta` 下发前端**：Runner 把这一 turn 的世界变化（对白、移动、关系、结局、节点转移）经 IPC → Flask → 前端，前端据此实时渲染并触发 **AIGC 出图**（连续+并发出图，画面体现 agent 情绪/对话气泡）。

### 4. 数据流与分层（各自在流程中的位置）

| 层 | 内容 | 在流程中干什么 |
| --- | --- | --- |
| **生成期工具（离线）** | `story_authoring/`（Designer/Producer/Writer） | **设计期**：把剧情需求编译成 Story Pack YAML。永不进运行期任何进程，只产数据。 |
| **L0 config（Story Pack）** | `config/stories/<id>/`（18 YAML + prompts + assets） | **所有故事差异的唯一来源**。启动期被 seed 进 world.db + 加载进解释器；运行期被各层只读。 |
| **L1 Runner** | 演员 agent（`hbm_agent.py`）+ 确定性解释器（`interpreter.py`）+ world_loop + kernel/seed | **运行期主体**。承载所有 LLM 调用（演员决策、裁判）；解释器做路由推进；引擎跑 memory/关系/移动。 |
| **L2 features** | f05_story_routing（解释器/StoryGraph）、f04_stats（评分）、f08_director（运行期裁判 agent）、f07_agent_control（选角/知识装配） | **可开关、可单测的特性**，与引擎生命周期解耦，由 L1 经 abcs 白名单调用。 |
| **L3 Flask（薄传输）** | `routes.py`（/session、/player_turn、/scenario） | **只传输 + session 管理**。session start 选 STORY_ID + 触发 validate；把 world_delta 经 IPC 下发前端。不做任何剧情判断，不承载 LLM。 |
| **前端 TS/TSX** | gameStore、storyAssets、EndingScreen、AIGC 渲染 | 从 session 下发的 `ui_text` payload **运行时注入**角色名/地点/结局/幕过渡；渲染世界 + 实时出图。 |

**端到端时序（文字版）**：`剧情需求 →[生成期工具]→ config/stories/<id>/ →[Flask session start: load+validate]→[Runner seed world.db]→ world_loop 起步 →（每 turn）玩家输入→tick→选角(读 node)→演员并发 LLM(读人设+memory+权限+行为卡)→引擎更新(memory/关系/移动/总线)→解释器读 story_graph 判转移+副作用→(裁判点) f08_director 产数据→endings 决策表选结局→world_delta 下发→前端渲染+AIGC 出图`。

### 5. 换故事时发生了什么

**只改 `config/stories/<id>/`，前后端代码零 diff**，上述流程的适配方式：

**自动适配（引擎/解释器/通用机制，完全不变）**：
- **memory 系统**：SegmentStore / compressor / perception 是通用引擎，新故事的对话照样自动累积、压缩、检索——换故事它就跑新世界的记忆，无需改代码（仅当 `memory.yaml` 配了初始记忆/健忘度才 overlay）。
- **关系实时变化**：`relation_change` 工具走通用 `RelationGraph`，新故事的关系突变（结盟/背刺）照样生效——只是初始关系网由新 `relations.yaml` 播种。
- **确定性解释器**：`interpreter.apply_routing()` 是表驱动 dispatch，遍历的是新 `story_graph.yaml` 的 nodes/edges——节点数、分岔、触发条件全换，但解释器代码一行不改。
- **消息总线 / overhear / 选角框架 / world_loop / tick**：全是通用机制，对故事无感知。
- **裁判 agent 框架**：f08_director 的 dispatch 不变，只是读新 `judges.yaml` 的维度和 prompt 模板。

**来自新配置（数据驱动，随包替换）**：
- **节点图**：`story_graph.yaml` 决定有几幕、怎么分岔、每个节点谁 active/frozen、玩家在哪、RDC 通讯对。
- **角色与关系**：`agents.yaml`（人设/role/faction/init_place/capabilities）+ `relations.yaml`（初始关系网）+ `prompts/`（人设 overlay + 初始记忆）。
- **能力**：`agents.yaml.capabilities` 决定哪些 agent 能调 story_advance；`timed_events` 决定运行期动态授予/撤销。
- **结局**：`endings.yaml` 决策表 + `judges.yaml` 裁判维度，决定如何根据（intent, 属性）判结局。
- **世界原语**：`places.yaml`（地点+coverage）、`place_behaviors.yaml`（地点变异）、`groups.yaml`、`timed_events.yaml`（时序事件）播种新世界。
- **前端呈现**：`ui_text.yaml` + `assets/` 随 session 下发，前端注入新角色名/地点/结局/幕过渡/立绘。

**一句话**：**引擎和解释器是"播放器"，Story Pack 是"碟片"**——换碟（改 config/stories/<id>/）就换一个完全不同的游戏（节点/角色/关系/memory/能力/结局都不同），而播放器（memory 引擎、关系引擎、确定性解释器、world_loop、消息总线、裁判框架、Flask 传输）一行代码不动。

---

**关键文件索引（绝对路径）**
- 设计依据：`/Users/dawson/Documents/GitHub/demo/dev_logs/{40,41,42,43}_*.md`
- 现状配置（待拆包）：`/Users/dawson/Documents/GitHub/demo/agent_world/hbm_demo/hbm_scenario.yaml`（relations L80-89 / capabilities L71-78 / coverage L57-69 / places L18-69 / agents L101-221）
- 现状 overlay（待迁入 prompts/）：`/Users/dawson/Documents/GitHub/demo/agent_world/hbm_demo/config/prompts/abcs/story_knowledge/{agents,shared}/*.yaml`
- 待新建：`shared/story_pack.py`、`shared/story_graph.py`、`features/f05_story_routing/interpreter.py`、`features/f08_director/`、`agent_world/hbm_demo/story_authoring/`、`config/stories/<id>/`
- 借鉴源：`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/agents/story_graph.py`（StoryGraph 直接抄）
