# 剧情与框架的解耦：换一套剧本要改哪里 + 如何做到"只改 config/ 就能换一个完全不同的故事"

> 由多智能体工作流并行精读全部耦合区域(6 区 + 综合)生成，已对照源码核验关键耦合点。
> 基线分支：story-framework-revamp（jensen-hwang-demo 基线，不含实时 AIGC）。


## 1. 概述：现状判断

HBM demo 早期的一项重要工作，是把 **提示词（prompt）外置到 `config/prompts/`**——`story_knowledge/agents/agent_*.yaml`、`shared/phase_*.yaml`、`turn_hints.yaml`、`plain_language.yaml` 等已经从 Python 字符串迁移成了 YAML。表面上看，"故事内容已经是配置了"。

但这只是**台词与人设的外置**，不是**剧情结构的外置**。当我们真正问"换一套剧本要改哪里"时，会发现以下七类东西仍然以 Python 常量、`if/elif` 分支、enum 白名单、LLM system prompt 的形式**写死在《HBM 显存价格保卫战》这一具体故事里**：

| 仍然硬编码的维度 | 典型表现 | 散落位置 |
| --- | --- | --- |
| **地点** | `nvidia_reception` / `jensen_private_room` / `negotiation_room` / `openai_hq` 四个 place_id 出现在多个模块的常量里 | `routing.py`、`agent_signals.py`、`f12_world_sync/constants.py`、`pick_active.py`、`web/utils/places.ts` |
| **角色** | Agent 1–7 的身份、阵营（NVIDIA `{2,3}` / CEO `{4,5,6}`）、玩家 = `agent 0` | `player_response.py`、`f12_world_sync/constants.py`、`web/constants/agents.ts` |
| **剧情结构** | 4 个 Phase、节点 A/B/C/D、Turn 16 事件、Turn 25 终局，全部以数字常量和 `if phase == "..."` 写死 | `routing.py`、`agent_signals.py`、`knowledge.py`、`handler.py`、`turn_control.yaml` |
| **路由** | 各 Phase 的 inject 目标、RDC 链路、node 检测函数（`detect_node_a/b/c`） | `routing.py`、`agent_signals.py`、`completion.py` |
| **结局** | `ending_join_nvidia` / `ending_seed_round` / `ending_cold_deal` / `bad_reject` 四个 id，trust≥25/≥15 阈值 | `routing.py`、`watcher.py`、`handler.py`、`f14_world_delta/handler.py`、`web/EndingScreen.tsx` |
| **裁判** | 评分 system prompt 写死了《HBM 显存价格保卫战》故事名 + 四维属性 + 技术关键词 | `f04_stats/scoring.py`、`routing.py`（turn25 / phase4 裁判 prompt） |
| **信号** | `story_advance` 的 6 个信号是 Python enum 白名单 `VALID_STORY_SIGNALS` | `story_signals.py`、`hbm_agent.py`（`STORY_ADVANCE_TOOL` 定义） |

**结论：换故事现在并不能"只改 config/"。** 即使把 `hbm_scenario.yaml` 和 `config/prompts/` 全部替换，路由引擎仍然会去找 `nvidia_reception`、去检测"前台(1)→Jensen(2)→VP(3)"的 RDC 链、去判定 trust≥25 给 `ending_join_nvidia`、去用"《HBM 显存价格保卫战》裁判"的 prompt 打分。新故事一旦改了地点名、角色编号、Phase 数量或结局命名，这些代码路径会直接失效或行为错乱。

本文把全部耦合点按"改 YAML 即可 / 必须改代码 / 框架级假设"三层逐一列出，并给出一个 **Story Pack** 配置结构与分阶段落地路线，目标是让"换一个完全不同的故事"退化成"替换一个 `config/stories/<story_id>/` 目录"。

---

## 2. 第一层：改 YAML 即可（数据已经在配置里，或迁移成本极低）

这一层的特征是：**值本身就是数据**（关键词、文案、阈值、映射表），代码已有或只需补一个"从 config 读取"的读取器即可。逐文件列出。

| 文件 | 位置 | 写死了什么 | config 化做法 |
| --- | --- | --- | --- |
| `hbm_scenario.yaml` | L1 `simulation_id` | 仿真 ID `hbm_memory_war` | 改名为 `<story_id>.yaml`，由 `metadata.simulation_id` 提供；运行时按 `STORY_ID` 环境变量/CLI 选择 |
| `hbm_scenario.yaml` | L7-8 `clock` | 起始 14:00、每 tick 2 分钟 | 移入 `timeline.start_time` / `minutes_per_tick`，不同故事可有不同时间压力 |
| `hbm_scenario.yaml` | L18-69 `places` | 4 个地点 id + summary + behavior_hint | 已是 YAML；拆到 `stories/<id>/places.yaml`，确保所有代码改为从此读取（见第二层） |
| `hbm_scenario.yaml` | L91-99 `groups` | group 100 (NVIDIA `[2,3]`) / 200 (HBM 联盟 `[4,5,6]`) | 已是 YAML；增加 `faction` 语义，前后端阵营判断改为查 `groups` |
| `hbm_scenario.yaml` | L101-221 `agents` | 7 个 agent 的 name/location/soul/goal/state | 已是 YAML；拆到 `stories/<id>/agents/*.yaml`，按 agent_id/role 加载 |
| `config/prompts/abcs/story_knowledge/shared/phase_1.yaml` | world_state / plot_beats / forbidden_actions | Phase 1 场景、节点 A 流程、禁止项 | 结构化为 `{locations, evaluation_criteria, node_sequence, constraints}`，地点/编号不再混在散文里 |
| 同上 `phase_2.yaml` | 全文 | Phase 2 私密审查、节点 B、PlaceMutation"死一般的寂静" | 同上；`node_b.side_effects[].place_mutation` 显式化 |
| 同上 `phase_3.yaml` | 全文 | Phase 3 全员战、Turn 16 AMD 广播、Samsung 背刺、节点 C | `turn_events[16]` + `node_c` 结构化 |
| 同上 `phase_4.yaml` | 全文 | Phase 4 终局、VP `silent_observer`、Turn 21-25、两结局 | `setup{present/silent/frozen}` + `endings[]` 结构化 |
| `story_knowledge/turn_hints.yaml` | L2-90 | Turn 1-25 全剧本片段 + 节点标记 + 信号触发 | 重构为 `[{turn, phase, node, events[], expected_signals[], cues[]}]` |
| `story_knowledge/shared/plain_language.yaml` | L1-15 | 禁用术语表、首选大白话、节点 B/C/deal 关键词 | 拆为 `{forbidden_terms[], preferred_phrases{}, magic_keywords{approval,dismissal,positive_eval}}` |
| `story_knowledge/agents/agent_1.yaml`…`agent_7.yaml` | 各文件 | 7 个角色身份、speech_style、phase_overrides、example_lines | 已是 YAML；提取出 `${company_name}`/`${leader_name}`/`${key_topic}` 占位符，台词模板化 |
| `config/prompts/abcs/turn_control.yaml` | L3-31 `phases` | 各 Phase 的 primary_active/passive/frozen 列表 | 已是 YAML；改造命名（见第三层 `Phase_1_passive`/`Phase_3_turn16` 问题） |
| `turn_control.yaml` | L27 `sam_rdc_from_turn: 16` | Sam 激活时刻 = Turn 16 | 改为 `activation_events[]` 通用时序事件 |
| `turn_control.yaml` | L33-39 `llm_params` | 各 Phase 温度/token，Turn 16 升温到 0.68 | 已是 YAML；命名通用化为 `{phase, mode/turn_trigger, temperature, max_tokens}` |
| `config/prompts/routing/routing.yaml` | `signals` 块 | approve/reject/expel/escort/return 关键词 | 已支持 YAML 覆盖；目标是让默认值也从此读，代码不留兜底（见第二层） |
| `routing.yaml` | `phase4_deal_keywords` | 20+ 成交预筛词 | 已支持 YAML 覆盖 |
| `routing.yaml` | `max_turns_phase1_without_approve: 10` | Phase 1 超时阈值 | 已参数化（`require_reception_escort_f2f` 同此） |
| `config/prompts/virtual_player/phase_places.yaml` | L2-8 | 玩家各 Phase 地点映射 | 已是 YAML；与 `f17/player_entity.py` 默认值需统一来源 |
| `f01_session/constants.py` | `INITIAL_STATS` | `trust=10, vision/execution/burnout=0` | 移到 `scenario.game_config.initial_stats` |
| `f01_session/constants.py` | `DEFAULT_SIM_ID` | `hbm_memory_war` | 改为从 `simulation_id` 读取 |
| `f04_stats/scoring.py` | L43 技术关键词 | `("显存","算法","80%","内存","优化","架构","降低")` | 移到 `scoring.tech_keywords`，换故事换一组（如"光刻/工艺制程/EUV"） |

> 这一层是"低垂果实"：大约一半的字段已经在 YAML 里，剩下的是把 Python 里的 dict/tuple 平移过去。**它能解决"换台词、换关键词、换文案"，但解决不了"换剧情结构"。**

---

## 3. 第二层：必须改代码（剧情逻辑硬编码在 Python/TS 里）

这一层的特征是：**值不是数据，是控制流**——`if phase == "Phase 1"`、`detect_node_a()` 里的 RDC 链、`resolve_ending_id()` 里的 `if trust >= 25`。把它们 config 化必须重构函数：把 `if/elif` 改成"遍历配置表"，把硬编码常量改成"查 scenario 对象"。

### 3.1 后端 Python

| 文件 | 行号 / 符号 | 写死了什么 | 如何 config 化 |
| --- | --- | --- | --- |
| `core/runner/hbm_agent.py` | L47-78 `STORY_ADVANCE_TOOL` | 6 个信号 enum + 每个信号的 Phase/动作中文描述 | 把 enum 和 description 模板迁到 `story_signals.yaml`，代码读 config 动态构造 tool schema |
| `hbm_agent.py` | L82-92 `_HBM_TOOLS_LIST` | 7 个工具的中文描述 | 迁到 `tools.yaml`（`name/description/allowed_for_agents/allowed_for_phases`），动态拼 prompt |
| `hbm_agent.py` | L233-367 `_hbm_short_action_rules()` | 240+ 行 agent×phase 行为矩阵（前台 RDC→Jensen、VP"可行/核武器"、清场关键词…） | 拆为模板系统：`agent_behaviors.yaml` 按 `(agent_id, phase, turn)` 定义行为卡（工具选择/参数约束/关键词检测/信号触发），代码遍历配置拼提示 |
| `hbm_agent.py` | L242-302（逐 Phase 逐 agent 分段） | 每个 `(aid, phase)` 组合的工具链与关键词（私人会议室/这边请/请离场…） | 同上，每段对应配置中一个声明式行为卡 |
| `features/f07_agent_control/knowledge.py` | L26-33 `_phase_key()` | `Phase 1`→`phase_1` 映射，Phase 数固定 4 | 移到 `{phase_names, phase_key_format}` 配置，代码生成映射 |
| `knowledge.py` | L56-61 `plain_language_section()` | 仅 agent 0/1 返回空，2-7 套通俗约束 | 改为 `{plain_language_agents: [2,3,4,5,6,7]}` |
| `knowledge.py` | L64-66 `load_agent_overlay()` | `agents/agent_{id}.yaml` 硬约定 | 支持别名/角色名加载 |
| `knowledge.py` | L207-305 `build_agent_knowledge()` | 组装逻辑对 `phase_overrides`/`response_checklist` 键名、`format_opening_directive` 调用硬依赖 | 改为配置驱动的模板渲染（`template_sections[]` + `section_config`） |
| `features/f07_agent_control/pick_active.py` | L28-29 | `SAM_ID=7`、`RECEPTION_AGENT_ID=1` | 迁到 `{special_agents:{sam:7, reception:1}}` |
| `pick_active.py` | L42-49 `_primary_ids()` | Phase 3 且 `turn>=16` 把 Sam 加入主动 | 改为通用 `activation_events[{turn:16, agent_activation:[7]}]` |
| `pick_active.py` | L87-89 `_in_negotiation_room()` | 硬编码 `negotiation_room` | 从 `places` 配置查 |
| `pick_active.py` | L121-132 `_reception_already_welcomed()` | 硬编码 `nvidia_reception` | 从 `reception_location` 配置查 |
| `features/f07_agent_control/conversation/control.py` | L192-212 | `if aid==3 / aid==1` 的 RDC 回复规则 | 迁到 `conversation_hints` 配置 |
| `control.py` | L235-272 | "节点 A"相关提示（F2F 后须 RDC→2、补 RDC…） | 迁到 `nodes.node_a.rules[]` 配置 |
| `features/f07_agent_control/player_response.py` | L7-18 `_AGENT_NAMES/_NVIDIA_IDS/_CEO_IDS` | 7 个中文名 + 阵营分组 | 从 scenario 的 `agents[].name` + `agents[].faction` 读 |
| `player_response.py` | L20-25 `_PHASE_OUTPUT_HINTS` | 各 Phase 输出长度（1–3 句…） | 迁到 `phases[].output_hint` |
| `player_response.py` | L32-131 `_phase_agent_extra()` | 全故事最核心的 agent×phase 行为约束 | 迁到 `agent_phase_behaviors{(agent_id,phase):{required_sequence,keywords,forbidden}}`，代码拼接 |
| `player_response.py` | L40-61 / L63-71 / L96-106 | 前台 P1、Jensen P1、Phase 3 阵营 + 清场规则 | 同上，逐条声明式化 |
| `features/f05_story_routing/routing.py` | L18-25 / L27-32 | place_id 常量 + agent id + `PHASE_INJECT_AGENTS` | 新增 `routing.yaml` 顶层 `places`/`agents`/`phase_agent_inject`，函数读 config |
| `routing.py` | L34-40 `POSITIVE_RDC_KEYWORDS` | `("可行","核武器","理论上成立"…)` | 迁到 `signals.tech_vp_approval_keywords` |
| `routing.py` | L42-51 | `TURN16_BROADCAST_MESSAGE`/`TURN16_SAM_TEXT`/`NODE_B_BEHAVIOR_HINT` | 迁到 `broadcast_triggers[]` + `special_messages{}` + `place_mutations.node_b` |
| `routing.py` | L54-60 `inject_agent_ids_for_phase()` | Phase 4 受 F07 控制时只注 Jensen | 改为查 `scenario.features.f07_enabled` + `phase_agent_inject` |
| `routing.py` | L123-135 `build_inject_payload()` | `player_turn==16 && phase=="Phase 3"` | 改为遍历 `broadcast_triggers[]` 查表触发 |
| `routing.py` | L207-215 `_heuristic_turn25_intent()` | join/seed 启发式关键词 | 迁到 `signals.intent_heuristics.{join,seed}_keywords` |
| `routing.py` | L252-257 `resolve_ending_id()` | `trust>=25→join, >=15→seed, else cold` | 迁到 `endings{id:{min_trust,label,desc}}`，查表替代 if 链 |
| `routing.py` | L260-281 `resolve_turn25_ending()` | `offer_join`/`offer_seed` 信号强制覆盖 | 迁到 `story_advance.signal_overrides[{signal,override_ending,priority}]` |
| `routing.py` | L360-383 `node_a_applies()` + `apply_routing()` | Node A：检测 Phase1→移 Jensen 到私室→转 Phase2 | 迁到 `routing_nodes.node_a{from_phase,to_phase,actions.agent_moves,state_updates}`，`apply_routing` 表驱动 |
| `routing.py` | L385-421 `node_b_applies()` | Node B：移 Jensen 到谈判室 + place_mutation + 转 Phase3 | 迁到 `routing_nodes.node_b`（含 `place_mutations[]`） |
| `routing.py` | L423-441 `node_c_applies()` | Node C：移 CEO[4,5,6] 回前台 + 转 Phase4 | 迁到 `routing_nodes.node_c` |
| `routing.py` | L63-67 `format_player_dialogue()` | `"玩家说：{text}"` 前缀 | 迁到 `format_templates.player_dialogue` |
| `features/f05_story_routing/agent_signals.py` | L20-28 | place/agent 常量**重复定义**（与 routing.py 同） | 抽到共享 `_constants.py` 或统一从 scenario 读，消除三处重复 |
| `agent_signals.py` | L94-121 `detect_node_a()` | 前台(1)→Jensen(2)→VP(3) RDC 链 + approval | 迁到 `node_detection.node_a.paths[]`（story_signal / rdc_chain / optional_f2f），查表执行 |
| `agent_signals.py` | L124-136 `detect_node_b()` | VP→Jensen 正面 RDC / Jensen 返回关键词 | 迁到 `node_detection.node_b.paths[]` |
| `agent_signals.py` | L139-162 `detect_node_c()` | Jensen→CEO 驱逐关键词 / 同室 F2F | 迁到 `node_detection.node_c.paths[]` |
| `agent_signals.py` | L223-242 `detect_bad_end()` | reject 信号 / 前台拒绝 / Phase1 超时 | 迁到 `bad_end_conditions[]` 遍历 |
| `features/f05_story_routing/story_signals.py` | L7-14 `VALID_STORY_SIGNALS` | 6 信号 enum 白名单 | 迁到 `story_signals.valid_signals[]`，`normalize_story_signal()` 读 config |
| `features/f05_story_routing/watcher.py` | L112-134 | bad_end 写死 `ending_id="bad_reject"` | 迁到 `bad_end.ending_id` |
| `watcher.py` | L141-169 `scan_routing_if_needed()` | Phase 4 早结束两路径（offer 信号 / LLM 判稿） | 迁到 `phase4_early_end.paths[]` 表驱动 |
| `features/f05_story_routing/routing_config.py` | L48-96 | 6 组关键词的**代码内默认值** | 让默认值也从 `routing.yaml` 读；缺字段时返回空 tuple 或记 warning，迫使显式配置 |
| `features/f02_player_turn/inject.py` | L38-44 `BAD_END_PUBLIC_MESSAGES` | "保安，请这位先生离开。" | 迁到 `bad_end.messages[{speaker_id,text}]` |
| `features/f02_player_turn/handler.py` | L56/L361 | `is_final_turn = player_turn == 25` | 迁到 `game_config.final_turn` |
| `handler.py` | L268 | bad_end id `"bad_reject"` | 迁到 `game_config.ending_ids` |
| `features/f03_action_result/completion.py` | L21-51 `PHASE_RDC_PAIRS` + place 常量 | 各 Phase 允许的 RDC 通讯对 + 重复 place 常量 | 迁到 `phases[].allowed_rdc_pairs`；place 常量统一来源 |
| `features/f14_world_delta/handler.py` | L80-88 | `if ending_id=="bad_reject" → game_over else completed` | 迁到 `ending_status_map{bad_reject:game_over, *:completed}` |
| `features/f12_world_sync/constants.py` | L10-15 | `HBM_ROOM_PLACES`(4 地点) + `HBM_AGENT_IDS`(1-7) | 改为 `get_story_places()`/`get_story_agent_ids()` 运行时读 scenario |
| `features/f17_virtual_player/player_entity.py` | L29-37 | 玩家各 Phase 地点的代码内默认字典 | 即使 `phase_places.yaml` 缺失，也从 scenario `player_journey` 读，不留硬编码兜底 |
| `features/f17_virtual_player/player_f2f.py` | L18-23 `_PHASE_RECIPIENT` | 玩家 F2F 对象：P1→1，P2/3/4→2 | 迁到 `phases[].player_f2f_recipient_id`，与 `phase_agent_inject` 统一 |

> **三段框架级 LLM 裁判 prompt**（标注 `3-framework-coupled` 但本质需要改代码读 config）：
> - `routing.py` L223-227 `classify_turn25_intent()`：system prompt 写死"你是《HBM 显存价格保卫战》结局裁判" + `join_nvidia|seed_round|ambiguous`。
> - `routing.py` L300-308 `classify_phase4_conclusion()`：写死故事背景 + 两结局定义。
> - `f04_stats/scoring.py` L70-74：评分 system prompt 写死故事名 + 四维属性。
>
> 三者都应改为从 `llm_prompts{}` / `scoring{game_title,dimensions}` 配置读取模板并格式化。`routing.py` L198-204 的 `base_url="https://api.deepseek.com"` 已可经 `load_scenario` 参数化，不算故事耦合，但建议确认 upstream 配置生效。

### 3.2 前端 TS/TSX

| 文件 | 位置 / 符号 | 写死了什么 | 如何 config 化 |
| --- | --- | --- | --- |
| `web/src/constants/agents.ts` | L3 `HBM_AGENT_IDS` | `[1..7]` 角色数量 | 从前端 config 读 `agent_roster.ids` |
| `agents.ts` | L7-15 `AGENT_DISPLAY_NAMES` | 7 个中文显示名 | 读 `agents{id:name}` |
| `agents.ts` | L17 `PLAYER_AGENT_ID` | `'player'` | 读 `player.agent_id` |
| `web/src/constants/groups.ts` | L3-6 `GROUP_LABELS` | `100='NVIDIA 核心高管群'`,`200='HBM 价格联盟'` | 读 `groups{id:label}` |
| `web/src/constants/gameLoop.ts` | L27 `PLAYER_SENDER` | `'玩家'` | 读 `player.sender_display_name` |
| `web/src/constants/phaseTransitions.ts` | L3-7 `PHASE_TRANSITIONS` | 3 段幕过渡文案 | 读 `phase_transitions{'P1->P2':...}` |
| `web/src/utils/places.ts` | L3-8 `ROOM_GRID` | 4 地点 id 顺序 | 读 `places.order[]` |
| `places.ts` | L12-17 `PLACE_LABELS` | 4 地点中文名 | 读 `places.labels{}` |
| `web/src/features/story-mode/storyAssets.ts` | L5-10 `PLACE_BACKGROUNDS` | 4 背景图路径 | 读 `places.backgrounds{}` |
| `storyAssets.ts` | L16 | 默认地点 `nvidia_reception` | 读 `game.default_start_place` |
| `storyAssets.ts` | L20-25 `storyAvatarUrl()` | 头像路径 `agent_{id}.png`/`player.png` | 读 `assets.avatars{}` |
| `web/src/features/endings/EndingScreen.tsx` | L1-4 `EndingId` 类型 | 3 结局 id 字面量 | 从 config 派生 `type EndingId = (typeof CONFIG.endings.ids)[number]` |
| `EndingScreen.tsx` | L6-25 `ENDING_COPY` | 3 结局完整文案（badge/title/description） | 读 `endings{id:{badge,title,description}}` |
| `web/src/features/endings/GameOverScreen.tsx` | L10-11 | bad end 默认标题/描述 | 读 `endings.bad_end{title,description}` |
| `web/src/App.tsx` | L256 | bad end 备选描述（与上重复） | 与 `GameOverScreen` 统一来源 |
| `web/src/store/gameStore.ts` | L27 `EndingId` 类型 | 派生 3 结局 id | 动态生成 |
| `gameStore.ts` | L81 | 初始 `phase='Phase 1'` | 读 `game.initial_phase` |
| `gameStore.ts` | L83 | 初始 `placeId='nvidia_reception'` | 读 `game.initial_place` |
| `web/src/api/types.ts` | L202 `PlayerTurnCompleted.ending_id` | 3 结局 id 联合类型 | 从后端 schema 生成或 const 断言 |
| `web/src/store/worldSync.ts` | L78 `mergeRoomF2f()` | 兜底默认地点 `nvidia_reception` | 读 `game.fallback_place` |

> 前端额外需要一条机制：**配置如何送达前端**。建议后端在 session 初始化时把 Story Pack 的"前端可见子集"（角色名、群名、地点名/顺序/背景、Phase 过渡文案、结局文案、初始 phase/place）随 `GET /scenario` 或首帧 world_delta 一起下发，前端 `constants/*` 改为运行时从该 payload 注入，而非 import 静态常量。

---

## 4. 第三层：框架耦合（散落在各处的隐式假设）

这一层不是某个具体值，而是**整个框架默认了"故事长什么样"**。即使把第一、二层全部 config 化，下列假设如果不显式参数化，仍会限制"完全不同的故事"。

1. **Phase 名格式 = `"Phase N"`，数量 = 4**：`knowledge.py:_phase_key()` 把 `"Phase 1"`→`"phase_1"`；`turn_control.yaml` 用 `Phase_1_passive`/`Phase_3_turn16` 这类拼接命名；几乎所有路由 `if phase == "Phase X"`。新故事若想要 3 幕或 6 幕、或非线性结构（分支幕），现框架无法表达。需要把 Phase 升格为**一等数据**：`phases: [{id, name, key, ...}]`，节点转换写成 `from_phase→to_phase` 的有向边而非数字递增。

2. **玩家 = `agent 0`**：前后端多处默认玩家是固定 id 0/`'player'`，且玩家恒为"一个外来访客"。若新故事玩家扮演已有角色之一、或有多名玩家，框架的 inject/F2F/打分路径都假设了单一外部玩家。

3. **结局数量 = 4（含 1 个 bad_end）+ 二维 trust 阈值**：`resolve_ending_id` 假设结局由 `(intent, trust)` 二维决定；`f14` 假设只有 `bad_reject` 映射 `game_over`。多结局/多维属性/中途分支结局都需要把"结局判定"从 if 链升格为**决策表/决策树**。

4. **"story_advance 信号"这套控制点本身是 HBM 设计的**：6 个信号、节点 A/B/C/D 的命名、"信号覆盖自然 RDC 检测"的优先级，都是为这个谈判故事量身定做。换一个非"逐幕推进 + 关键 RDC 链"的故事（如开放探索、多线并行），信号语义需要重新定义——这属于框架级改造而非配 config。

5. **RDC 链 / F2F / 群聊三种交互原语 + 阵营二分**：`_NVIDIA_IDS`/`_CEO_IDS` 把世界二分为"我方/敌方"。多阵营、动态结盟（已部分体现在 Samsung 背刺的 `relation_change`）若要成为常态，需要把"阵营"做成 n 路 `faction` 图。

6. **裁判维度固定四维（vision/execution/trust/burnout）**：评分 prompt 和 `INITIAL_STATS` 都假设这四维。不同题材可能要"声望/资金/健康/线索"等任意维度——属性表需要可变长。

> 第三层的判断原则：**凡是"数量/结构/语义"被框架默认死的，都是真正的框架改造**；凡是"具体取值"被写死的，归第一、二层。

---

## 5. 同构 vs 异构判断：什么时候工作量小，什么时候是框架大改

把"换故事"按与 HBM 的结构相似度分两类：

### 5.1 同构故事（structure-isomorphic）—— 工作量小

特征：**同样是"4 幕逐步推进 + 关键 RDC 链解锁 + trust 驱动多结局 + 单一外来玩家"**，只是换皮——换公司/角色/地点/术语/结局文案。

例：把"19 岁天才向 NVIDIA 推销省显存算法"换成"独立制片人向好莱坞六大推销剧本"——前台→制片主管→CEO→竞争片厂→流媒体搅局者，幕结构、节点条件、信号语义可一一对应。

此类**只需第一层 + 第二层的"数据外置"**，不碰第三层：只要把所有 place_id / agent / 关键词 / 文案 / 阈值 / prompt 模板搬进 Story Pack，路由的 `detect_node_*`、`apply_routing`、`resolve_ending_id` 改成读表即可。**这正是本文"只改 config"要瞄准的目标场景**——做完后,同构故事真的只改 `config/stories/<id>/`。

### 5.2 异构故事（structure-divergent）—— 框架大改

任一为真即落入此类：
- Phase 数 ≠ 4 或非线性（分支/并行幕）；
- 玩家不是单一外来访客（扮已有角色 / 多玩家）；
- 推进机制不是"关键 RDC 链 + story_advance 信号"（开放探索、时间驱动、资源经营）；
- 属性维度 ≠ 四维，或结局判定 ≠ `(intent, trust)`。

此类必须先做**第三层框架改造**：Phase 升格为数据图、玩家身份参数化、信号机制泛化为"可配置的状态机转换"、属性/结局表变长。这不是配 config 能覆盖的，需要重构 `routing.py`/`agent_signals.py`/`knowledge.py` 的核心控制流，把"HBM 专用的节点 A/B/C/D 状态机"替换成"读 Story Pack 定义的通用状态机解释器"。

**一句话标准**：换皮 → 第一二层（config 化即可）；换骨 → 第三层（框架级）。

---

## 6. 重点章节：如何做到"只改 config/ 就能换故事"

目标：换一个**同构**故事，只需新增/替换一个目录 `config/stories/<story_id>/`，运行时通过 `STORY_ID` 选择，全部 Python/TS 不动。下面给出 **Story Pack** 的结构设计、建议 schema，以及每个代码文件"改成从该 config 读取"的具体做法。

### 6.1 Story Pack 目录结构

```
config/stories/<story_id>/
├── meta.yaml            # simulation_id / 故事名 / 时间线 / 初始 phase&place / final_turn
├── places.yaml          # 地点表：id / label / 邻接 / 背景图 / behavior_hint
├── agents.yaml          # 角色表：id / name / role / faction / 初始位置 / soul引用
├── groups.yaml          # 阵营/群组表
├── phases.yaml          # 幕列表：参与者 / 玩家位置 / F2F对象 / RDC对 / 输出约束 / llm参数
├── routing_nodes.yaml   # 节点 A/B/C…：from_phase→to_phase / 检测路径 / 动作 / 副作用
├── signals.yaml         # story_advance 信号白名单 + tool描述 + 关键词集合
├── endings.yaml         # 结局表：id / 触发条件 / 文案 / game状态映射 / bad_end
├── judges.yaml          # 裁判：评分维度 / 技术关键词 / 各 LLM prompt 模板
├── timed_events.yaml     # 时序事件：Turn N 广播 / agent 激活 / inject
├── language_style.yaml   # 禁用术语 / 首选大白话 / magic_keywords
├── ui_text.yaml          # 前端文案：角色名 / 群名 / 幕过渡 / 结局 / 初始phase&place
├── prompts/             # agent 人设 overlay（沿用现 story_knowledge/agents/*）
└── assets/              # 背景图 / 头像（或仅约定路径规则）
```

### 6.2 各文件建议 schema（关键字段）

`meta.yaml`
```yaml
simulation_id: hbm_memory_war
story_name: "《HBM 显存价格保卫战》"
timeline: { start_time: "14:00", minutes_per_tick: 2 }
game_config:
  initial_phase: "Phase 1"
  initial_place: nvidia_reception
  final_turn: 25
  initial_stats: { vision: 0, execution: 0, trust: 10, burnout: 0 }
player: { agent_id: 0, frontend_id: "player", sender_display_name: "玩家" }
```

`places.yaml`
```yaml
places:
  - { id: nvidia_reception, label: "英伟达总部 · 接待前台", background: "/assets/.../nvidia_reception_bg.webp", behavior_hint: "..." }
  - { id: jensen_private_room, label: "黄仁勋私人会议室", ... }
order: [nvidia_reception, jensen_private_room, negotiation_room, openai_hq]
fallback_place: nvidia_reception
```

`agents.yaml`
```yaml
agents:
  - { id: 1, name: "接待前台", role: receptionist, faction: nvidia, init_place: nvidia_reception, overlay: prompts/agent_1.yaml }
  - { id: 2, name: "Jensen Hwang", role: leader, faction: nvidia, init_place: negotiation_room, overlay: prompts/agent_2.yaml }
  # ...
roles: { reception: 1, leader: 2, tech_vp: 3, suppliers: [4,5,6], disruptor: 7 }
factions: { nvidia: [2,3], suppliers: [4,5,6] }
```

`phases.yaml`
```yaml
phases:
  - id: "Phase 1"
    key: phase_1
    inject_agents: [1]
    player_place: nvidia_reception
    player_f2f_recipient: 1
    allowed_rdc_pairs: [[1,2]]
    output_hint: "1–3 句口语"
    active: { primary: [1,2,3], passive: [4,5,6], frozen: [7] }
    llm: { temperature: 0.45, max_tokens: 180, passive: { temperature: 0.35, max_tokens: 120 } }
  # Phase 2 / 3 / 4 ...
```

`routing_nodes.yaml`
```yaml
nodes:
  node_a:
    from_phase: "Phase 1"
    to_phase: "Phase 2"
    detection:
      paths:
        - { type: story_signal, signal: approve_visitor }
        - { type: rdc_chain, chain: [[1,2],[2,3]], approval: { sender: 2, recipient: 1, keywords_ref: approve_keywords } }
    actions: { agent_moves: [{ agent: leader, dest: jensen_private_room }] }
    state_updates: { tick_field: phase2_start_tick }
  node_b:
    from_phase: "Phase 2"; to_phase: "Phase 3"
    actions:
      agent_moves: [{ agent: leader, dest: negotiation_room }]
      place_mutations: [{ place: negotiation_room, behavior_hint: "死一般的寂静…" }]
  node_c:
    from_phase: "Phase 3"; to_phase: "Phase 4"
    actions: { agent_moves: [{ agents: suppliers, dest: nvidia_reception }] }
bad_end:
  ending_id: bad_reject
  conditions:
    - { type: story_signal, signal: reject_visitor }
    - { type: reception_reject, place: nvidia_reception, agent: reception, keywords_ref: reject_keywords }
    - { type: phase_timeout, phase: "Phase 1", max_turns: 10 }
  messages: [{ speaker: reception, text: "保安，请这位先生离开。" }]
```

`signals.yaml`
```yaml
story_advance:
  enabled: true
  valid_signals:
    - { name: approve_visitor, phase: "Phase 1", desc: "Jensen 批准前台后调用" }
    - { name: return_to_negotiation, phase: "Phase 2", desc: "..." }
    - { name: expel_ceos, phase: "Phase 3", desc: "..." }
    - { name: offer_join, phase: "Phase 4", override_ending: ending_join_nvidia }
    - { name: offer_seed, phase: "Phase 4", override_ending: ending_seed_round }
    - { name: reject_visitor, phase: "Phase 1" }
keywords:
  approve_keywords: ["私人会议室","这边请","请跟我来","批准", ...]
  reject_keywords: ["拒绝","请离开","保安"]
  expel_keywords: ["请离场","谈完了","请出去", ...]
  escort_keywords: ["请跟我来","这边请"]
  return_to_negotiation_keywords: ["回谈判室","进谈判室","认可", ...]
  tech_vp_approval_keywords: ["可行","核武器","理论上成立","理论上可行","成立"]
  phase4_deal_keywords: ["offer","合同","入职","融资", ...]
```

`endings.yaml`
```yaml
endings:
  - { id: ending_join_nvidia, intent: join_nvidia, min_trust: 25, status: completed, badge: "结局 A", title: "加入 NVIDIA", description: "...", frontend: true }
  - { id: ending_seed_round,  intent: seed_round,  min_trust: 15, status: completed, badge: "结局 B", title: "独立融资", description: "..." }
  - { id: ending_cold_deal,   intent: "*",         min_trust: 0,  status: completed, badge: "结局 C", title: "冷处理协议", description: "..." }
  - { id: bad_reject, status: game_over, title: "Bad End · 被请出大楼", description: "..." }
intent_heuristics:
  join_nvidia_keywords: ["加入","入职","nvidia","团队","全职"]
  seed_round_keywords: ["融资","种子","投资","独立","创业"]
```

`judges.yaml`
```yaml
scoring:
  game_title: "《HBM 显存价格保卫战》"
  dimensions: [vision, execution, trust, burnout]
  tech_keywords: ["显存","算法","80%","内存","优化","架构","降低"]
  system_prompt: "你是{game_title}裁判，按 {dimensions} 四维打分…"
llm_prompts:
  turn25_intent_system: "你是{game_title}结局裁判…只输出 {intents}…"
  phase4_conclusion_system: "你是{game_title}终局裁判…{ending_descriptions}…"
ending_descriptions: { join_nvidia: "玩家加入NVIDIA", seed_round: "玩家拿NVIDIA投资独立创业" }
```

`timed_events.yaml`
```yaml
events:
  - turn: 16
    phase: "Phase 3"
    broadcast: "彭博终端快讯：AMD 宣布下一代 MI400…"
    inject: { agent: disruptor, text: "系统指令：OpenAI 对稀疏注意力算法极度感兴趣…" }
    activate_agents: [disruptor]
    enable: [samsung_betrayal]
```

`ui_text.yaml`（前端可见子集，随 session 下发）
```yaml
agents: { "1": "接待前台", "2": "Jensen", ... }
groups: { "100": "NVIDIA 核心高管群", "200": "HBM 价格联盟" }
phase_transitions: { "Phase 1->Phase 2": "前台带你进入私密会议室…", ... }
endings: { ending_join_nvidia: { badge: "结局 A", title: "加入 NVIDIA", description: "..." }, ... }
init: { phase: "Phase 1", place: nvidia_reception }
```

### 6.3 各代码文件"改成从该 config 读取"的具体做法

- **统一常量源**：新建 `features/f05_story_routing/_constants.py`（或 `shared/story_constants.py`），暴露 `places()`/`agent_id(role)`/`faction(name)`/`phase_inject(phase)`，内部都走 `load_story_pack()`。删除 `routing.py`、`agent_signals.py`、`f12_world_sync/constants.py`、`completion.py` 里重复的 `PLACE_*`/`JENSEN_ID`/`CEO_IDS`，改为 `from ._constants import ...`。
- **`routing.py`：node 状态机表驱动**。`apply_routing()` 不再写 `if node_a_applies(): ...`，改为 `for node in story.routing_nodes: if detect(node, ...): apply(node.actions)`。`detect()` 解释 `detection.paths[]`（story_signal / rdc_chain / f2f）；`apply()` 解释 `actions.agent_moves` / `place_mutations` / `state_updates`。`resolve_ending_id()`/`resolve_turn25_ending()` 改为遍历 `endings[]`（先查 `signal_overrides`，再按 `intent + min_trust` 命中）。`build_inject_payload()` 改为遍历 `timed_events[]` 匹配 `(turn, phase)`。三段 LLM prompt 改为 `judges.yaml` 模板 `.format(**story_vars)`。
- **`agent_signals.py`：`detect_node_*` 退化为通用 `detect_path()`**。把三个函数合并成一个按 `node_detection.paths[]` 解释的检测器，关键词全部经 `keywords[ref]` 解引用。
- **`story_signals.py`：`VALID_STORY_SIGNALS` 改为 `load_story_pack().signals.valid_signals`**，`normalize_story_signal()` 用 config 白名单。
- **`hbm_agent.py`：`STORY_ADVANCE_TOOL` / `_HBM_TOOLS_LIST` 动态构造**，enum 与 description 来自 `signals.yaml` / `tools.yaml`。`_hbm_short_action_rules()` 与 `player_response._phase_agent_extra()` 改为渲染 `agent_phase_behaviors`（按 `(agent_id, phase)` 取行为卡 → 模板拼装），不再写 `if aid == 1 and phase == "Phase 1"`。
- **`knowledge.py`：`_phase_key()` / `plain_language_section()`** 读 `phases[].key` 与 `language_style.plain_language_agents`；`build_agent_knowledge()` 按 `template_sections` 渲染。
- **`pick_active.py` / `completion.py` / `f17` / `f02` / `f14`**：所有 `== "nvidia_reception"` / `== 25` / `== "bad_reject"` 改为查 `places()` / `game_config.final_turn` / `endings` 表。
- **`f04_stats/scoring.py`**：`tech_keywords` 与 system prompt 读 `judges.yaml`。
- **前端**：`constants/*`、`utils/places.ts`、`storyAssets.ts`、`EndingScreen.tsx`、`gameStore.ts`、`worldSync.ts` 全部从后端下发的 `ui_text` payload 注入，删除静态中文常量；`EndingId`/`api/types.ts` 由 `endings.ids` 派生。

做完以上，**同构换故事 = 写一个新的 `config/stories/<id>/` + 设 `STORY_ID`**，代码零改动。

---

## 7. 落地路线（分阶段，可独立验证）

每阶段都保持"现有 HBM 行为不变（回归通过）+ 新增一条可独立验证的能力"，全程守 `npm run build` + gate 门禁。

### 阶段一：抽字符串与映射（角色名 / 地点 / 文案）
- **范围**：第一层全部 + 第二层中"纯值"的部分——`_AGENT_NAMES`、`GROUP_LABELS`、`PLACE_LABELS`、`PHASE_TRANSITIONS`、`ENDING_COPY`、`INITIAL_STATS`、`BAD_END_PUBLIC_MESSAGES`、`tech_keywords`、各关键词 tuple 的默认值。建立 `load_story_pack()` 读取器与前端 `ui_text` 下发通道，但**路由控制流先不动**（仍走旧常量，新常量从 config 读后断言相等）。
- **验证**：单测断言"从 config 读出的值 == 旧硬编码值"；前后端跑一局完整 HBM，行为逐帧对齐旧版（snapshot）。门禁：gate + `npm run build` 绿。

### 阶段二：抽 Phase / 路由 / 信号为数据驱动
- **范围**：第二层核心——`routing.py` 的 `apply_routing`/`node_*_applies`、`agent_signals.py` 的 `detect_node_*`、`PHASE_INJECT_AGENTS`、`PHASE_RDC_PAIRS`、`VALID_STORY_SIGNALS`、`STORY_ADVANCE_TOOL`、`timed_events`(Turn 16)。把 if 链改为表驱动解释器。
- **验证**：用现有 HBM 的 `routing_nodes.yaml`/`signals.yaml`/`phases.yaml` 喂解释器，跑回归脚本走完 Phase1→2→3→4 + Turn 16 事件 + bad_end 三条路径，结局/转场/inject 与旧版一致。再造一个**最小同构 demo 故事**（改地点名/角色名/Phase 数仍 4）验证"只改 config 能跑"。门禁同上。

### 阶段三：抽结局与裁判
- **范围**：`resolve_ending_id`/`resolve_turn25_ending`/`classify_turn25_intent`/`classify_phase4_conclusion`/`scoring.py`/`f14` 的 `ending_status_map`。结局判定从 if 链 → `endings[]` 决策表；三段 LLM prompt → `judges.yaml` 模板。
- **验证**：固定一组 `(intent, trust)` 输入，断言 `resolve_ending_id` 表驱动结果 == 旧 if 链结果（覆盖 25/15 边界）；prompt 渲染快照比对。LLM 裁判用录制的对话回放校验分类稳定。门禁同上。

### 阶段四：前端文案化与素材约定
- **范围**：前端彻底去静态常量，`constants/*`、`storyAssets.ts`、`EndingScreen.tsx`、`gameStore.ts`、`worldSync.ts`、`api/types.ts` 全部从 `ui_text` payload 注入；约定 `assets/` 路径规则（背景 `places[].background`、头像 `assets.avatars{}`）。
- **验证**：换一套占位文案/占位图的 `ui_text`，前端不改一行代码即呈现新角色名/地点名/结局文案/幕过渡。E2E 跑同构 demo 故事，UI 全程显示新故事文案。`npm run build` + 视觉 snapshot 绿。

**完成标志**：把阶段二造的"最小同构 demo 故事"扩成一个完整、与 HBM 题材完全不同的同构剧本，仅新增 `config/stories/<new_id>/` 并设 `STORY_ID=<new_id>`，前后端代码零 diff，即可端到端跑通——届时"只改 config/ 就能换一个完全不同的故事"对**同构故事**成立；异构故事则进入第三层框架改造的独立议题。

---
