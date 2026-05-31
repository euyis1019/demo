# 把 HBM Demo 改成「只改 config/stories/ 就能换一个完全不同的游戏」——并回答「要不要 Phase」

> 由多智能体工作流(phase 审计 + 三方案竞标 + 综合)生成。配套 dev_logs/40(耦合清单)、dev_logs/41(AI4VisualNovel 借鉴)。
> 基线分支：story-framework-revamp。


> 配套 dev_logs/40（剧情耦合点全清单 + Story Pack 方向）、dev_logs/41（参考 AI4VisualNovel 的 DAG/解释器借鉴）。本文是把这两篇收口成**可照着做的完整修改规划**，并对「Phase 该不该存在」给出明确结论。
> 基线：当前 4 硬编码 Phase + 路由节点 A/B/C/D + 3+1 结局 + 四维裁判，逻辑写死在 `features/f05_story_routing/routing.py`、`agent_signals.py`、`core/runner/hbm_agent.py`、`features/f04_stats/scoring.py`、`features/f07_agent_control/pick_active.py`。

---

## 1. 为什么要有 Phase / 该不该去掉

### 1.1 Phase 今天到底承担了什么职责（审计结论）

把现状源码里所有读 `phase` 字符串的地方归类,Phase 实际驱动了 **16 个控制点**,分散在 8 个文件:

| # | 控制点 | 位置（核验后的真实符号） | 删掉 phase 会怎样 | 在 DAG 模型里挂到哪 |
| --- | --- | --- | --- | --- |
| 1 | 路由推进 | `routing.py:apply_routing()` L338 内 `node_a/b/c_applies()` | 无法换幕 | `edge.from→to` + `edge.trigger` |
| 2 | inject 目标 | `routing.py:inject_agent_ids_for_phase()` L54、`PHASE_INJECT_AGENTS` L27 | inject 给错人 | `node.inject_agents` |
| 3 | L3 主被动调度 | `pick_active.py:_primary_ids()` L42、`turn_control.yaml:phases` | 谁说话乱 | `node.active{primary,passive,frozen}` |
| 4 | 知识装配 | `knowledge.py:_phase_key()` L26 `"Phase 1"→"phase_1"` | overlay 找不到 | `node.knowledge_key` |
| 5 | LLM 参数 | `turn_control.yaml:llm_params`（按 phase 名拼 key） | 温度/token 错 | `node.llm` |
| 6 | agent 行为卡 | `hbm_agent.py:_hbm_short_action_rules()` L233 `if aid==1 and phase=="Phase 1"` | agent 行为错 | `node.agent_behaviors[aid]` |
| 7 | UI 幕过渡 | `web/constants/phaseTransitions.ts`、`gameStore.ts` L81 | 无转场 | `node.beats_label` + 边推导 |
| 8 | 状态追踪 | `session.phase`、`phase2_start_tick`… | 计时丢 | `session.current_node_id` + `node_start_ticks` |
| 9 | bad_end 检测 | `agent_signals.py:detect_bad_end()` L223（Phase1 超时） | 坏结局漏判 | `bad_end.conditions[].phase_timeout` |
| 10 | Phase 4 早结束 | `watcher.py:scan_routing_if_needed()`、`classify_phase4_conclusion()` L284 | 终局判错 | `node.early_end` 出边 |
| 11 | 结局选择 | `routing.py:resolve_ending_id()` L252 `if trust>=25` | 结局判错 | `endings[].when` 决策表 |
| 12 | 玩家同步 | `player_f2f.py:_PHASE_RECIPIENT`、`player_entity.py` 默认字典 | 玩家走错地点 | `node.player_place` / `player_f2f_recipient` |
| 13 | 裁判维度 | `scoring.py` L43/L69（按四维 + 故事名） | 打分跑偏 | `judges.dimensions`(+可选 `node.epoch` 调权) |
| 14 | recap/对白前缀 | `routing.py:format_player_dialogue()` L63 | 文案错 | `format_templates` |
| 15 | 被动时序事件 | `routing.py:build_inject_payload()` L89 `turn==16 and phase=="Phase 3"` | Turn16 错过 | `timed_events[].node_filter` |
| 16 | 前置约束/RDC 对 | `completion.py:PHASE_RDC_PAIRS` L21、`agent_signals.detect_node_*` | RDC 链卡死 | `node.allowed_rdc_pairs` + `edge.trigger.rdc_chain` |

**审计判决:Phase 这个"阶段流"概念是必要的——游戏确实需要"分步骤推进";但 Phase 这个"全局字符串状态变量"不是必要的。** 现今 4 个 Phase 本质是上述 16 个控制点的**粗粒度分组标签**,它把"节点转移"编码成了硬编码字符串(`"Phase 1/2/3/4"`)而不是显式节点 ID。这些控制点本该挂在**节点配置**或**边的元数据**上,却被拆散成散落各处的 `if phase ==` 比较。

### 1.2 为什么"一条线多结局"用 DAG 表达更自然

现状的多结局靠 `resolve_ending_id()` 里 `if trust>=25→join / >=15→seed / else cold` 二维阈值,bad_end 又另起一套 `detect_bad_end()`。这有三个结构性问题:

1. **结局判定与推进逻辑割裂**——推进走 phase 字符串,结局走 trust 阈值,bad_end 走第三套检测,三处各自硬编码,改一个故事要改三处。
2. **"分岔"无法表达**——Phase 假设线性递增(1→2→3→4),但"加入 NVIDIA"和"独立融资"本是从 Phase 3 分出的两条**不同路径**。线性 phase 字符串表达不了分岔,只能用 trust 阈值"事后补判"。
3. **题材被锁死**——3 幕、6 幕、非线性(并行任务/Hub-spoke)都无法用"Phase N"线性序列表达(dev_logs/40 §4 第三层结论)。

DAG 天然解决:`root→phase2→phase3→ending_join` 和 `root→phase2→phase3→ending_seed` 是**两条共享前缀、末端分岔**的路径,节点 ID + 边的 trigger 足以区分,无需任何全局字符串。同一个 DAG 既能按"幕序列"展示给玩家,也能按"功能分组"给开发者看——**数据与呈现解耦**。

### 1.3 明确结论(推荐处理)

**推荐:采用方案 B 的"Phase 降级为节点元数据",而非方案 A 的"彻底删除 phase 字段"。**

- **删除 Phase 作为控制流变量**:所有 `if phase == "Phase X"` 一律删除,真正的路由状态变成 `session.current_node_id`;所有 16 个控制点改为读 `story.get_node(current_node_id)` 的配置。
- **保留 Phase 作为只读数据标签**:节点上保留 `beats_label: "Phase 1"`(供前端显示"第几幕"、裁判分段、API 向后兼容);`session.phase` 退化为 `story.get_node(current_node_id).beats_label` 的只读导出,绝不可直接赋值。

理由:方案 A 完全去掉 phase 字段会破坏前端 `PlayerTurnCompleted.phase` / `world_delta.phase` 的 API 兼容(dev_logs 三方案的 migration_risk 都点了这个),而保留为 `beats_label` 数据标签零成本,且让"4 幕/3 幕/非线性"全部可参数化。方案 C 的 `epoch` 调权特性(裁判按幕调权重)作为**可选增量**保留——`epoch_feature_enabled: false` 时不启用,HBM 当前不需要,但留好扩展点。

**一句话:Phase 概念保留(数据标签),Phase 字符串变量删除(用 node_id 替代)。**

---

## 2. 推荐的目标模型

### 2.1 三方案评审与选型

| | A 纯节点图(去 phase 字段) | **B Phase 降级为元数据** | C act-epoch 混合 |
| --- | --- | --- | --- |
| 推进机制 | `current_node_id` 图遍历 | `current_node_id` 图遍历 | `current_node_id` 图遍历 |
| phase 字段 | 删除 | **保留为 `beats_label` 只读标签** | 保留为 `epoch` 可选标签 |
| API 兼容 | 破坏(需新增 node_id 协议) | **兼容(phase 从 label 读)** | 兼容 |
| 裁判按幕调权 | 无 | 无(可后加) | 内建 `epoch_weights` |
| 迁移成本 | 中(API 改造) | **低(label 平移)** | 中(多一层 epoch 语义) |

**选 B,融入 C 的 epoch 可选扩展点。** B 是 A 与 C 的折中:既彻底去掉 phase 控制流(=A 的核心收益),又用零成本的 `beats_label` 保住 API 与前端显示(避开 A 的迁移坑);C 的 `epoch_weights` 调权作为 `judges.yaml` 的可选块挂上,HBM 默认不开。三方案的 schema/解释器骨架本就一致(都是 DAG+dispatch),取舍只在"phase 字段保不保、怎么保",B 的答案最省。

### 2.2 最终故事数据模型

```
StoryPack
├── Node     节点 = 一个"游戏关卡/幕"
│   { id, beats_label, node_type:{normal|merge|ending},
│     active_agents, frozen_agents, inject_agents,
│     player_place, player_f2f_recipient, allowed_rdc_pairs,
│     output_hint, llm, knowledge_key, scoring, epoch?,
│     ending_id?, status? }            # ending 节点专属
├── Edge     边 = node A → node B 的转移
│   { from, to, edge_id, trigger, actions, priority }
├── Trigger  触发条件(命中即可转移)
│   any_of:[ story_signal | rdc_chain | rdc_positive | rdc_expel |
│            reception_reject | phase_timeout | turn_timeout |
│            condition(safe_eval) ]
├── Action   命中后的副作用
│   { agent_moves, place_mutations, state_updates, inject, broadcast }
├── Ending   结局决策表
│   [{ id, override_signal?, when?, priority, status,
│      badge, title, description, frontend }]   + bad_end{}
├── Judge    裁判
│   { game_title, dimensions, tech_keywords,
│     llm_prompts{turn25_intent, phase4_conclusion, scoring},
│     epoch_weights? }
├── Actors   { agents[], roles{role→id}, factions{name→[id]} }
├── Places   { places[], order[], fallback_place }
└── Player   { agent_id, frontend_id, sender_display_name }
```

核心不变量(加载期 `validate()` 强制):必有 `root` 节点;无环;每个非 ending 节点有出边(无死路);所有 ending 可达;每条边的 `rdc_chain` 的 pair ⊆ `from_node.allowed_rdc_pairs`;每个引用的 role/place/agent 都能解引用。

---

## 3. 完整 Story Pack 配置结构与 schema

```
config/stories/<story_id>/
├── meta.yaml            # simulation_id / 故事名 / 时间线 / 初始 node / final_turn / 初始属性 / 玩家
├── story_graph.yaml     # ★ DAG: nodes + edges（替代 routing.py/agent_signals.py 的 if 链）
├── places.yaml          # 地点表
├── agents.yaml          # 角色表 + roles + factions
├── groups.yaml          # 群组/阵营显示
├── signals.yaml         # story_advance 白名单 + 工具描述 + keyword_sets
├── endings.yaml         # 结局决策表 + bad_end
├── judges.yaml          # 裁判维度 + 技术关键词 + 三段 LLM prompt 模板
├── timed_events.yaml    # Turn N 广播/激活/inject
├── language_style.yaml  # 禁用术语 / 大白话 / plain_language_agents
├── ui_text.yaml         # 前端可见子集（随 session 下发）
├── prompts/             # agent 人设 overlay（沿用现 story_knowledge/agents/*）
└── assets/              # 背景图 / 头像
```

下面给出**覆盖现有 HBM 全部行为**的关键 schema(`meta/places/agents/groups/language_style/ui_text` 沿用 dev_logs/40 §6.2,此处只展开三方案讨论后细化的核心三件:`story_graph`、`signals`、`endings`、`judges`、`timed_events`)。

### story_graph.yaml(节点 + 边)

```yaml
metadata:
  story_id: hbm_memory_war
  root_node_id: root

nodes:
  root:
    id: root
    beats_label: "Phase 1"           # 只读显示，不驱动逻辑
    node_type: normal
    knowledge_key: phase_1           # 替代 _phase_key() 的 "Phase 1"→"phase_1"
    active_agents: [1, 2, 3]
    passive_agents: [4, 5, 6]
    frozen_agents: [7]
    inject_agents: [1]               # 替代 PHASE_INJECT_AGENTS["Phase 1"]
    player_place: nvidia_reception
    player_f2f_recipient: 1
    allowed_rdc_pairs: [[1, 2]]      # 替代 completion.py:PHASE_RDC_PAIRS
    output_hint: "1-3 句口语"
    llm: { temperature: 0.45, max_tokens: 180,
           passive: { temperature: 0.35, max_tokens: 120 } }
    scoring: { enabled: true }

  phase2:
    id: phase2
    beats_label: "Phase 2"
    node_type: normal
    knowledge_key: phase_2
    active_agents: [2]
    frozen_agents: [4, 5, 6, 7]
    inject_agents: [2]
    player_place: jensen_private_room
    player_f2f_recipient: 2
    allowed_rdc_pairs: [[2, 3]]
    llm: { temperature: 0.35, max_tokens: 120 }

  phase3:
    id: phase3
    beats_label: "Phase 3"
    node_type: merge                 # A/B 线汇合点
    knowledge_key: phase_3
    active_agents: [2, 3, 4, 5, 6]
    frozen_agents: [7]
    inject_agents: [2, 3, 4, 5, 6]
    player_place: negotiation_room
    player_f2f_recipient: 2
    allowed_rdc_pairs: [[2, 3], [2, 4], [2, 5], [2, 6]]

  phase4:
    id: phase4
    beats_label: "Phase 4"
    node_type: normal
    knowledge_key: phase_4
    active_agents: [2, 3, 7]
    inject_agents: [2]               # F07 控制下只注 Jensen（替代 inject_agent_ids_for_phase 特例）
    player_place: negotiation_room
    player_f2f_recipient: 2
    early_end: true                  # 触发 phase4_conclusion LLM 早结束判定

  ending_join:
    { id: ending_join, node_type: ending, beats_label: "结局 A",
      ending_id: ending_join_nvidia, status: completed }
  ending_seed:
    { id: ending_seed, node_type: ending, beats_label: "结局 B",
      ending_id: ending_seed_round, status: completed }
  ending_cold:
    { id: ending_cold, node_type: ending, beats_label: "结局 C",
      ending_id: ending_cold_deal, status: completed }
  bad_end:
    { id: bad_end, node_type: ending, beats_label: "Bad End",
      ending_id: bad_reject, status: game_over }

edges:
  # 原 node_a：Phase1→Phase2（替代 agent_signals.detect_node_a + routing apply 段）
  - from: root
    to: phase2
    edge_id: "root->phase2"
    priority: 10
    trigger:
      any_of:
        - { type: story_signal, signal: approve_visitor }
        - { type: rdc_chain, chain: [[1, 2], [2, 3]],
            approval: { sender_role: leader, recipient_role: reception,
                        keywords_ref: approve_keywords } }
    actions:
      agent_moves: [{ agent_role: leader, dest: jensen_private_room }]
      state_updates: { phase2_start_tick: "$current_tick" }

  # bad_end（替代 detect_bad_end）—— 优先级高于正常推进
  - from: root
    to: bad_end
    edge_id: "root->bad_end"
    priority: 20
    trigger:
      any_of:
        - { type: story_signal, signal: reject_visitor }
        - { type: reception_reject, place: nvidia_reception,
            agent_role: reception, keywords_ref: reject_keywords }
        - { type: phase_timeout, from_node: root, max_turns: 10 }
    actions:
      inject: { agent_role: reception, text: "保安，请这位先生离开。" }

  # 原 node_b：Phase2→Phase3 + place_mutation（替代 detect_node_b + node_b_applies）
  - from: phase2
    to: phase3
    edge_id: "phase2->phase3"
    priority: 10
    trigger:
      rdc_positive: { sender_role: tech_vp, recipient_role: leader,
                      keywords_ref: tech_vp_approval_keywords }
    actions:
      agent_moves: [{ agent_role: leader, dest: negotiation_room }]
      place_mutations: [{ place: negotiation_room, behavior_hint_ref: node_b_hint }]
      state_updates: { phase3_start_tick: "$current_tick" }

  # 原 node_c：Phase3→Phase4（替代 detect_node_c + node_c_applies）
  - from: phase3
    to: phase4
    edge_id: "phase3->phase4"
    priority: 10
    trigger:
      rdc_expel: { sender_role: leader, recipients_role: suppliers,
                   keywords_ref: expel_keywords }
    actions:
      agent_moves: [{ agents_role: suppliers, dest: nvidia_reception }]
      state_updates: { phase4_start_tick: "$current_tick" }

  # Phase4 → 结局（实际结局由 endings.yaml 决策表选 ending_id；这里只是图转移占位）
  - { from: phase4, to: ending_join, edge_id: "p4->join", priority: 15,
      trigger: { ending_ref: ending_join_nvidia } }
  - { from: phase4, to: ending_seed, edge_id: "p4->seed", priority: 14,
      trigger: { ending_ref: ending_seed_round } }
  - { from: phase4, to: ending_cold, edge_id: "p4->cold", priority: 0,
      trigger: { ending_ref: ending_cold_deal } }
```

### signals.yaml(`story_advance` 白名单 + 关键词总表)

```yaml
story_advance:
  enabled: true
  valid_signals:                     # 替代 story_signals.py:VALID_STORY_SIGNALS
    - { name: approve_visitor,       node_context: [root],   desc: "Jensen 批准访客" }
    - { name: return_to_negotiation, node_context: [phase2], desc: "玩家返回谈判室" }
    - { name: expel_ceos,            node_context: [phase3], desc: "Jensen 驱逐 CEO" }
    - { name: offer_join,  node_context: [phase4], override_ending: ending_join_nvidia }
    - { name: offer_seed,  node_context: [phase4], override_ending: ending_seed_round }
    - { name: reject_visitor,        node_context: [root],   desc: "前台拒绝访客" }

keyword_sets:                        # 所有 keywords_ref 在此解引用，消灭硬编码 tuple
  approve_keywords:  ["私人会议室", "这边请", "请跟我来", "批准", "同意"]
  reject_keywords:   ["拒绝", "请离开", "保安", "不见"]
  expel_keywords:    ["请离场", "谈完了", "请出去", "送客"]
  escort_keywords:   ["请跟我来", "这边请"]
  return_to_negotiation_keywords: ["回谈判室", "进谈判室", "认可"]
  tech_vp_approval_keywords: ["可行", "核武器", "理论上成立", "理论上可行", "成立"]  # = routing.POSITIVE_RDC_KEYWORDS
  phase4_deal_keywords: ["offer", "合同", "入职", "融资"]

intent_heuristics:                   # 替代 routing._heuristic_turn25_intent
  join_nvidia: ["加入", "入职", "nvidia", "团队", "全职"]
  seed_round:  ["融资", "种子", "投资", "独立", "创业"]
```

### endings.yaml(决策表替代 if 链)

```yaml
endings:
  # 优先级 10：signal 覆盖（替代 resolve_turn25_ending 的 offer_* 强制覆盖）
  - { id: ending_join_nvidia, override_signal: offer_join, priority: 10,
      status: completed, badge: "结局 A", title: "加入 NVIDIA", description: "...", frontend: true }
  - { id: ending_seed_round,  override_signal: offer_seed, priority: 10,
      status: completed, badge: "结局 B", title: "独立融资", description: "...", frontend: true }
  # 优先级 5：表达式（替代 resolve_ending_id 的 trust 阈值 if 链）
  - { id: ending_join_nvidia, when: "intent == 'join_nvidia' and trust >= 25", priority: 5 }
  - { id: ending_seed_round,  when: "intent == 'seed_round'  and trust >= 15", priority: 5 }
  # 优先级 0：兜底
  - { id: ending_cold_deal,   when: "true", priority: 0,
      status: completed, badge: "结局 C", title: "冷处理协议", description: "...", frontend: true }
fallback_ending: ending_cold_deal

bad_end:                             # 替代 detect_bad_end + watcher 写死 "bad_reject"
  id: bad_reject
  status: game_over                  # 替代 f14 的 ending_status_map
  badge: "Bad End"
  title: "被请出大楼"
  description: "保安将你带出了大楼。"
```

### judges.yaml(裁判模板化)

```yaml
scoring:                             # 替代 scoring.py L43/L69 写死
  game_title: "《HBM 显存价格保卫战》"
  dimensions: [vision, execution, trust, burnout]
  tech_keywords: ["显存", "算法", "80%", "内存", "优化", "架构", "降低"]
  system_prompt: |
    你是{game_title}的游戏裁判。根据对话记录，按 {dimensions_str} 四维评估玩家表现。
    输出 JSON：{{"vision":..,"execution":..,"trust":..,"burnout":..}}
  # epoch_weights:  ← 方案 C 可选块，HBM 默认不配
llm_prompts:
  turn25_intent_system: |            # 替代 classify_turn25_intent
    你是{game_title}的结局裁判。判断玩家最终意图，仅输出：join_nvidia | seed_round | ambiguous
  phase4_conclusion_system: |        # 替代 classify_phase4_conclusion
    你是{game_title}的终局裁判。{ending_descriptions} 判断 Phase 4 是否应结束：true/false
ending_descriptions:
  join_nvidia: "玩家加入 NVIDIA"
  seed_round: "玩家拿 NVIDIA 投资独立创业"
```

### timed_events.yaml(Turn N 事件)

```yaml
events:
  - turn: 16
    node_filter: [phase3]            # 替代 build_inject_payload 的 turn==16 && phase=="Phase 3"
    broadcast: "彭博终端快讯：AMD 宣布下一代 MI400…"
    inject: { agent_role: disruptor, text: "系统指令：OpenAI 对稀疏注意力算法极度感兴趣…" }
    activate_agents: [disruptor]     # 替代 pick_active._primary_ids 的 turn>=16 加 Sam
    enable_features: [samsung_betrayal]
```

---

## 3.5 现有 HBM 故事作为该 schema 的实例(可表达性证明)

上节的 YAML **就是**把今天硬编码逻辑逐条翻译成 config 的实例。逐条对照证明覆盖:

| 今天的硬编码 | 真实符号/行号 | 翻译成 config |
| --- | --- | --- |
| Phase 1→2 推进 | `agent_signals.detect_node_a` L94 + `apply_routing` L360 搬 Jensen 到私室 | `root→phase2` 边的 `rdc_chain` trigger + `agent_moves` action |
| Phase 2→3 + 死寂 | `detect_node_b` L124 + `node_b_applies` L168 + `NODE_B_BEHAVIOR_HINT` L49 | `phase2→phase3` 边 `rdc_positive` + `place_mutations(node_b_hint)` |
| Phase 3→4 清场 | `detect_node_c` L139 + `node_c_applies` L183 CEO[4,5,6]→前台 | `phase3→phase4` 边 `rdc_expel(suppliers)` + `agent_moves` |
| Turn16 AMD广播+Sam激活 | `build_inject_payload` L89 `turn==16 && phase=="Phase 3"` + `pick_active._primary_ids` L42 turn≥16 加 Sam | `timed_events[turn:16, node_filter:[phase3]]` |
| bad_end(拒绝/超时) | `detect_bad_end` L223 + `watcher` 写死 `bad_reject` | `root→bad_end` 边三条 trigger + `endings.bad_end` |
| 3 好结局 trust 阈值 | `resolve_ending_id` L252 / `resolve_turn25_ending` L260 | `endings[]` 决策表(override + when + fallback) |
| 四维裁判 | `scoring.py` L43/L69 写死故事名+四维+技术词 | `judges.scoring` |
| inject 目标 | `PHASE_INJECT_AGENTS` L27 + `inject_agent_ids_for_phase` L54 | `node.inject_agents`(Phase4 特例 → `phase4.inject_agents:[2]`) |
| RDC 通讯对 | `completion.PHASE_RDC_PAIRS` L21 | `node.allowed_rdc_pairs` |
| place/agent 常量三处重复 | `routing.py` L18-24、`agent_signals.py` L21-28 | `places.yaml`+`agents.roles{reception:1,leader:2,tech_vp:3,suppliers:[4,5,6],disruptor:7}` |
| 信号白名单 | `story_signals.VALID_STORY_SIGNALS` L7 | `signals.valid_signals` |
| 技术关键词 | `scoring.py` L43 `("显存","算法",…)` | `judges.tech_keywords` |

每一条都有对应的 config 落点,无遗漏 —— **现有 HBM 可被该 schema 完整表达**。

---

## 4. 运行期改造(通用图解释器)

新建两个文件,逐个替代硬编码。

### 4.1 `shared/story_graph.py`(直接抄 AI4VN)

```python
class StoryGraph:                       # 抄 AI4VisualNovel/agents/story_graph.py
    def __init__(self, data):
        self.nodes = data["nodes"]
        self.edges = data["edges"]
        self._adj = self._build_adjacency()
    def get_edges_from(self, node_id):  # 出边按 priority 降序
        return sorted([e for e in self.edges if e["from"] == node_id],
                      key=lambda e: -e.get("priority", 0))
    def get_node(self, node_id): return self.nodes.get(node_id)
    def is_ending(self, node_id): return self.get_node(node_id)["node_type"] == "ending"
    def validate(self):                 # 加载期门禁：无环 + root 存在 + 结局可达 + 无死路
        ...
    def get_reachable_endings(self): ...
    def enumerate_all_paths(self): ...   # 回归测试用
```

### 4.2 `features/f05_story_routing/interpreter.py`(detect/apply dispatch 表)

```python
# ---- 触发条件 dispatch（替代 agent_signals.detect_node_a/b/c + detect_bad_end）----
TRIGGER_HANDLERS = {
    "story_signal":    lambda s, ctx: has_story_signal(ctx.db, s["signal"], **ctx.window),
    "rdc_chain":       lambda s, ctx: _rdc_chain(ctx, s),       # detect_node_a 逻辑
    "rdc_positive":    lambda s, ctx: _rdc_positive(ctx, s),    # detect_node_b 逻辑
    "rdc_expel":       lambda s, ctx: _rdc_expel(ctx, s),       # detect_node_c 逻辑
    "reception_reject":lambda s, ctx: _reception_reject(ctx, s),
    "phase_timeout":   lambda s, ctx: ctx.turns_in_node(s["from_node"]) >= s["max_turns"],
    "condition":       lambda s, ctx: safe_eval(s["expr"], ctx.vars()),
    "ending_ref":      lambda s, ctx: False,  # 图转移占位，实际由 resolve_ending 决定
}
def detect(trigger, ctx):
    if not trigger: return True
    if "any_of" in trigger:
        return any(detect(t, ctx) for t in trigger["any_of"])
    (kind, spec), = trigger.items()
    h = TRIGGER_HANDLERS.get(kind)
    if not h: log.warning("unknown trigger %s", kind); return False
    return h(spec, ctx)

# ---- 副作用 dispatch（替代 apply_routing 里手写的 send_move_agent 序列）----
ACTION_HANDLERS = {
    "agent_moves":     lambda s, ctx: [ctx.move(ctx.role_to_id(m.get("agent_role") or m.get("agents_role")), m["dest"]) for m in s],
    "place_mutations": lambda s, ctx: [ctx.mutate_place(m["place"], ctx.hint(m)) for m in s],
    "state_updates":   lambda s, ctx: ctx.update_state(_resolve_vars(s, ctx)),  # $current_tick → ctx.current_tick
    "inject":          lambda s, ctx: ctx.inject(ctx.role_to_id(s["agent_role"]), s["text"]),
    "broadcast":       lambda s, ctx: ctx.broadcast(s),
}
def apply_actions(actions, ctx):
    for kind, spec in actions.items():
        h = ACTION_HANDLERS.get(kind)
        if h: h(spec, ctx)
        else: log.warning("unknown action %s", kind)

# ---- 主路由（替代 routing.apply_routing 的三个 if 块）----
def apply_routing(session, *, ipc_client, db, current_tick, **kw):
    story = load_story_graph(session.story_id)
    ctx = RoutingCtx(session, db, ipc_client, current_tick, story)
    _process_timed_events(story, ctx)            # 替代 build_inject_payload 的 turn==16
    for edge in story.get_edges_from(session.current_node_id):   # 邻接表，零 if 链
        if detect(edge["trigger"], ctx):
            apply_actions(edge.get("actions", {}), ctx)
            to = story.get_node(edge["to"])
            session.current_node_id = edge["to"]
            session.phase = to["beats_label"]    # phase 从数据读，只读导出
            if story.is_ending(edge["to"]):
                session.ending_id = to["ending_id"]
                session.game_status = to.get("status", "completed")
            return {"nodes": [edge["to"]], "transition": edge["edge_id"]}
    return {"nodes": []}

# ---- 结局决策表（替代 resolve_ending_id L252 + resolve_turn25_ending L260）----
def resolve_ending(session, db, *, since_t, t_now):
    spec = load_endings(session.story_id)
    for rule in sorted(spec["endings"], key=lambda r: -r.get("priority", 0)):
        if "override_signal" in rule and has_story_signal(db, rule["override_signal"], since_t=since_t, t_now=t_now):
            return rule["id"]
        if "when" in rule and safe_eval(rule["when"], session.vars()):
            return rule["id"]
    return spec["fallback_ending"]
```

### 4.3 安全表达式求值器 `safe_eval`

白名单变量 `{trust, intent, beats_label, turn, flags}`,用 `ast` 解析,只允许比较/布尔运算(`>= <= == != and or not`),禁函数调用/属性访问/下标。建议引入 `simpleeval` 或自研受限编译器,**禁用 Python `eval()`**(注入风险)。覆盖现有 4 结局条件的单测必须全绿(含 `trust==25`/`trust==15` 边界)。

### 4.4 其余硬编码的替代

- `hbm_agent.py:_hbm_short_action_rules()` L233(240+ 行 `if aid==N and phase=="Phase X"`)→ `build_agent_prompt(aid, session, story)`:从 `node.active_agents/frozen_agents/agent_behaviors[aid]` 读,模板拼装(借 AI4VN `ActorAgent._build_system_prompt` 的纯模板渲染)。
- `pick_active.py:_primary_ids()` L42 → 读 `node.active{primary,passive,frozen}`;`SAM_ID/RECEPTION_AGENT_ID` → 查 `agents.roles`。
- `scoring.py` L43/L69 → 读 `judges.scoring`。
- `story_signals.normalize_story_signal` → 读 `signals.valid_signals`。

---

## 5. 逐文件改造清单

### 后端 Python(基于 dev_logs/40 §3.1,按目标模型细化)

| 文件 | 改成什么 |
| --- | --- |
| **新增** `shared/story_graph.py` | 抄 AI4VN `StoryGraph`(`get_edges_from/get_node/is_ending/validate/get_reachable_endings/enumerate_all_paths`) |
| **新增** `features/f05_story_routing/interpreter.py` | `detect/apply_actions/apply_routing/resolve_ending` + `TRIGGER_HANDLERS/ACTION_HANDLERS` |
| **新增** `shared/story_pack.py` | `load_story_pack/load_story_graph/load_endings/load_signals/load_judges`;`role_to_id/place/faction` 解引用,`safe_eval` |
| `routing.py` | 删 L18-51 常量;`apply_routing`/`node_*_applies`/`resolve_ending_id`/`resolve_turn25_ending`/`build_inject_payload`/`inject_agent_ids_for_phase` 全部委托 interpreter;三段 LLM prompt 改读 `judges.yaml` 模板 `.format()` |
| `agent_signals.py` | `detect_node_a/b/c`/`detect_bad_end` 合并进 `TRIGGER_HANDLERS`;删 L21-28 重复常量,改 `from shared.story_pack import role_to_id` |
| `story_signals.py` | `VALID_STORY_SIGNALS`→`load_signals().valid_signals` |
| `watcher.py` | `scan_routing_if_needed` 早结束读 `node.early_end`;`bad_reject` 写死 → `endings.bad_end.id` |
| `core/runner/hbm_agent.py` | `STORY_ADVANCE_TOOL`/`_HBM_TOOLS_LIST` 动态构造(读 `signals.yaml`/`tools.yaml`);`_hbm_short_action_rules` → `build_agent_prompt` 模板渲染 |
| `f07_agent_control/knowledge.py` | `_phase_key`→`node.knowledge_key`;`plain_language_section`→`language_style.plain_language_agents` |
| `f07_agent_control/pick_active.py` | `_primary_ids`→`node.active`;`SAM_ID/RECEPTION_AGENT_ID`→`roles`;`_in_negotiation_room/_reception_already_welcomed`→查 `places` |
| `f07_agent_control/player_response.py` | `_AGENT_NAMES/_NVIDIA_IDS/_CEO_IDS`→`agents[].name/faction`;`_PHASE_OUTPUT_HINTS`→`node.output_hint`;`_phase_agent_extra`→`node.agent_behaviors` |
| `f07_agent_control/conversation/control.py` | `if aid==3/aid==1` RDC 规则、节点 A 提示 → `node.conversation_hints` |
| `f03_action_result/completion.py` | `PHASE_RDC_PAIRS`→`node.allowed_rdc_pairs`;place 常量统一来源 |
| `f04_stats/scoring.py` | `tech_keywords` + system prompt → `judges.yaml` |
| `f02_player_turn/handler.py` | `player_turn==25`→`game_config.final_turn`;`"bad_reject"`→`endings.ids` |
| `f02_player_turn/inject.py` | `BAD_END_PUBLIC_MESSAGES`→边的 `inject` action / `endings.bad_end.messages` |
| `f14_world_delta/handler.py` | `if ending_id=="bad_reject"`→`endings[].status` 查表 |
| `f12_world_sync/constants.py` | `HBM_ROOM_PLACES/HBM_AGENT_IDS`→`get_story_places()/get_story_agent_ids()` |
| `f17_virtual_player/player_entity.py`、`player_f2f.py` | 玩家各 phase 地点/F2F → `node.player_place`/`player_f2f_recipient` |
| `f01_session/constants.py` | `INITIAL_STATS`→`meta.game_config.initial_stats`;`DEFAULT_SIM_ID`→`metadata.simulation_id` |

### 前端 TS/TSX(全部从 session 下发的 `ui_text` payload 运行时注入)

| 文件 | 改成什么 |
| --- | --- |
| `constants/agents.ts` | `HBM_AGENT_IDS/AGENT_DISPLAY_NAMES/PLAYER_AGENT_ID`→读 `ui_text.agents` |
| `constants/groups.ts` | `GROUP_LABELS`→`ui_text.groups` |
| `constants/phaseTransitions.ts` | `PHASE_TRANSITIONS`→`ui_text.phase_transitions` |
| `constants/gameLoop.ts` | `PLAYER_SENDER`→`ui_text.player.sender_display_name` |
| `utils/places.ts` | `ROOM_GRID/PLACE_LABELS`→`ui_text.places.order/labels` |
| `features/story-mode/storyAssets.ts` | `PLACE_BACKGROUNDS`/默认地点/`storyAvatarUrl`→`ui_text.places.backgrounds`/`assets.avatars` |
| `features/endings/EndingScreen.tsx` | `EndingId`/`ENDING_COPY`→`ui_text.endings`,类型从 config 派生 |
| `features/endings/GameOverScreen.tsx`、`App.tsx` | bad end 文案 → `ui_text.endings.bad_end` 统一来源 |
| `store/gameStore.ts` | 初始 `phase/placeId`/`EndingId`→`ui_text.init` |
| `store/worldSync.ts` | 兜底地点 → `ui_text.places.fallback` |
| `api/types.ts` | `ending_id` 联合类型从 `endings.ids` 派生 |
| **新增下发通道** | 后端 session 初始化时把 Story Pack 前端可见子集编译成 JSON,随 `GET /scenario` 或首帧 world_delta 下发 |

---

## 6. 分阶段落地路线

全程守 `npm run build` + gate 门禁;每阶段保持现有 HBM 行为不变(snapshot 逐帧对齐)。**★ 标注可直接借 AI4VN。**

### 阶段一:抽字符串与映射(纯值平移)
- **范围**:dev_logs/40 第一层全部 + 第二层纯值(`_AGENT_NAMES`、`GROUP_LABELS`、`PLACE_LABELS`、`PHASE_TRANSITIONS`、`ENDING_COPY`、`INITIAL_STATS`、`BAD_END_PUBLIC_MESSAGES`、`tech_keywords`、各关键词 tuple)。建 `load_story_pack()` + 前端 `ui_text` 下发通道。**路由控制流先不动**:新常量从 config 读后**断言 == 旧硬编码值**。
- **验证**:单测断言"config 值 == 旧值";跑一局完整 HBM,snapshot 逐帧对齐。

### 阶段二:抽 Phase/路由/信号为数据驱动(★ AI4VN 最大加速点)
- **范围**:`story_graph.py`(★抄 AI4VN)+ `interpreter.py`(detect/apply)。`apply_routing`/`node_*_applies`/`detect_node_*`/`PHASE_INJECT_AGENTS`/`PHASE_RDC_PAIRS`/`VALID_STORY_SIGNALS`/`STORY_ADVANCE_TOOL`/Turn16 事件一次性表驱动化。`story_graph.yaml` 用 `STORY_GRAPH_SCHEMA`+`jsonschema`(★)校验,加载期跑 `validate()`/`get_reachable_endings()`(★)做门禁。
- **验证**:用现有 HBM 的 `story_graph.yaml` 喂解释器,跑回归走完 Phase1→4 + Turn16 + bad_end 三路径,转移/inject/ending **逐帧等价**旧版;`enumerate_all_paths()`(★)断言四条路径仍存在。再造**最小同构 demo 故事**(改地点名/角色名,phase 仍 4)验证"只改 config 能跑"。

### 阶段三:抽结局与裁判(★ 中等加速)
- **范围**:`resolve_ending_id`/`resolve_turn25_ending`/`classify_turn25_intent`/`classify_phase4_conclusion`/`scoring.py`/`f14` 的 `ending_status_map`。结局 → `endings.yaml` 决策表 + `safe_eval`(★借 AI4VN `[IF]` 模型);三段 LLM prompt → `judges.yaml` 模板。
- **验证**:固定 `(intent, trust)` 输入,断言决策表结果 == 旧 if 链(覆盖 25/15 边界);prompt 渲染 snapshot 比对;LLM 裁判用录制对话回放校验分类稳定。

### 阶段四:前端文案化与素材约定
- **范围**:前端彻底去静态常量,全部从 `ui_text` payload 注入;约定 `assets/` 路径规则。
- **验证**:换占位 `ui_text`,前端零改一行即呈现新角色名/地点/结局/幕过渡;E2E 跑同构 demo 故事,UI 全程新文案;`npm run build` + 视觉 snapshot 绿。

### 最小同构 demo 故事验收闭环
1. 阶段二造 `config/stories/min_demo/`(改地点名/角色名,phase 仍 4,结局仍 3+1)。
2. `STORY_ID=min_demo` 启动,加载期 `validate()` 通过。
3. 端到端跑通 Phase1→4 + Turn16 事件 + bad_end 三路径,**前后端代码零 diff**。
4. `enumerate_all_paths()` 断言四条结局路径都可达。
5. 绿 → "改剧情不碰硬代码也能跑 phase"对同构故事成立。

---

## 7. 验收标准

### 同构故事(目标场景,本规划要达成)
"只改 config 就能换游戏"成立的判据:新增/替换一个 `config/stories/<id>/` 目录(8 个 YAML + `prompts/` + `assets/`),设 `STORY_ID=<id>`,**前后端代码零 diff**,即可端到端跑通,满足:
- 加载期 `validate()` 通过(无环、root 存在、结局可达、无死路、RDC 对子集校验、role/place 解引用成功);
- 推进、inject、bad_end、结局、裁判、UI 全部由 config 驱动,无任何 `if phase ==`;
- `enumerate_all_paths()` 断言所有声明的结局都可达;
- 前端显示的角色名/地点/结局/幕过渡全来自 `ui_text`。

同构定义:仍是"逐幕推进 + 关键 RDC 链/信号解锁 + 属性驱动多结局 + 单一外来玩家",只换皮(公司/角色/地点/术语/结局/属性词)。

### 异构故事(超出本规划,标注为后续议题)
任一为真即异构,**不在本规划范围**(需 dev_logs/40 §4 第三层框架改造):
- phase 数非线性(分支/并行幕);玩家不是单一外来访客(扮已有角色/多玩家);
- 推进机制不是"RDC 链 + story_advance 信号"(开放探索/时间驱动/资源经营);
- 属性维度变长或结局判定超出 `(intent, 属性)` 表达式。

注:本规划的 DAG 模型已为异构留好骨架(`node_type:merge`、任意节点数、`condition` 表达式),异构主要还差"玩家身份参数化"和"信号机制泛化",可在 DAG 之上增量演进而非推倒。

---

## 8. 风险与回退

| 风险 | 缓解 | 回退 |
| --- | --- | --- |
| 新旧引擎不等价(边优先级顺序偏离) | 阶段二 snapshot 逐 turn 对比 + `enumerate_all_paths` 断言四路径;新引擎走 `apply_routing_v2`,旧版保留 | 切回旧 `apply_routing` 一行开关 |
| Phase 字符串 API 兼容破坏 | 保留 `session.phase` 字段,从 `beats_label` 读;不改 `PlayerTurnCompleted.phase` 协议 | `beats_label` 与旧 phase 字符串一一对应,无需改客户端 |
| `safe_eval` 注入/求值错 | 禁 `eval()`,用 `ast` 白名单(只比较/布尔);覆盖 4 结局条件单测含边界;`simpleeval` 兜底 | 该故事 `endings` 退回硬编码 `resolve_ending_id` |
| `allowed_rdc_pairs` 漏配致边卡死 | 加载期校验 `edge.rdc_chain.pairs ⊆ node.allowed_rdc_pairs` | 加载期失败即拒绝启动,不进运行期 |
| agent 行为卡缺字段崩溃 | schema 必填或默认值;加载期 dry-run 所有 `(aid, node)` 对 | 降级到"默认行为"提示词 |
| Turn16 `node_filter` 错过(玩家快/慢) | 用"turn 范围 + 到达 node 即补注"而非精确 `turn==16 && node==phase3` | 该事件退回 `build_inject_payload` 硬编码 |
| `any_of` 误当 AND | schema 禁深层嵌套;复杂逻辑统一走 `condition` 表达式 | 文档明确 `any_of` 为 OR |
| 前端 `ui_text` 与后端 graph 漂移 | E2E 强制校验下发的 `ui_text` 与 `story_graph` 的 agents/places/endings 一致 | 前端保留旧静态常量作 fallback |
| 配置引用死数据(unknown role/place) | 加载期 `resolveRole/resolvePlace` 全量 dry-run,任一失败报错 | 加载期失败拒绝启动 |

**总体回退策略**:阶段二/三保留旧代码路径(`apply_routing` vs `apply_routing_v2`、`resolve_ending_id` vs `resolve_ending`),用单一开关切换;只有 snapshot 100% 对齐 + `enumerate_all_paths` 四路径全绿,才删旧路径。每阶段独立 PR,gate + `npm run build` 绿才合。

---

## 9. 补全(完备性审查后增补):World Primitives 与 Agent overlay 的 Story Pack 落点

§3 的 Story Pack 把"叙事控制流"(story_graph/signals/endings/judges/timed_events)规划完整了,但**漏掉了"世界原语播种"这一排**——`relations / capabilities / coverage / place_mutation / 初始 memory / perception`。这些现在写在 `hbm_scenario.yaml` 里由 `kernel.seed_world()` 播种,必须随包替换才能"换 config 换世界"。本节增补它们的落点。

### 9.1 新增/扩展的文件与字段

| 要素 | 现状位置 | 补到 Story Pack |
|------|---------|----------------|
| **初始关系网 relations**(关键遗漏) | `hbm_scenario.yaml` `relations:` → `RelationGraph.add()` | **★新增 `relations.yaml`**:`[{src_role,dst_role,type,symmetric,metadata?}]`,src/dst 用 `agents.roles` 解引用。**运行期实时变化(结盟/背刺)由通用 `relation_change` 工具驱动,无需故事配置——引擎已通用。** |
| **能力 capabilities** | `hbm_scenario.yaml` `capabilities:` → `CapabilityTable.grant()` | `agents.yaml` 每 agent 补 `capabilities:[...]`;运行期动态授予走 `timed_events` 的 `capability_grant/revoke` action。 |
| **连通性 coverage** | `hbm_scenario.yaml` `coverage:` | 并入 `places.yaml`:`coverage:[{src_place,dst_place,latency_ticks,can_reach}]`。 |
| **地点变异 place_mutation** | `routing.py:NODE_B_BEHAVIOR_HINT` 硬写 + `attrs.behavior_hint` | **★新增 `place_behaviors.yaml`**:`{place:{initial_behavior_hint,mutations:[{label,text}]}}`;边/timed_events 的 `place_mutations` 引用 `label`。 |
| **初始 memory** | 无 seed 接口(`SegmentStore` 仅运行期自动累积) | **★新增 `memory.yaml`(可选)**:`initial_memories:{agent_role:[{created_at,content,importance,tags}]}` + `segment_compressor` 策略。需补 `SegmentStore` seed 接口。**默认不配时引擎通用。** |
| **perception 感知** | `world/perception.py` 写死(F2F/旁听/RDC 优先级) | **★新增 `perception.yaml`(可选)**:per-agent per-modality 过滤。**默认全开通用,仅"某 agent 不该听同室"才配。** |
| **agent soul/goal/state、行为卡** | `scenario.agents[].soul`、`hbm_agent._hbm_short_action_rules` | `agents.yaml` 扩 `soul_template/long_term_goal/initial_state`;行为卡迁 `story_graph` 的 `node.agent_behaviors{aid:{respond_rule,length_rule,tool_constraints}}`。 |
| **knowledge/memory overlay** | `config/prompts/abcs/story_knowledge/{agents,shared}/*.yaml` | 整目录迁 `config/stories/<id>/prompts/`(含 `initial_memory` 段);`knowledge.py:load_agent_overlay()` 改按 `story_id` 查路径。 |
| **群组动态成员、可用工具白名单、tools** | `groups`(初始)、`hbm_agent` 工具描述 | `timed_events.group_action`;`signals.valid_signals` 动态拼 tool;可选 `tools.yaml`。 |
| overhear / direct_message / 两类 log / 消息总线 | 引擎 + world.db | **引擎已通用无需配置**(overhear 是 F2F 衍生,log 是审计自动生成,与故事无关)。 |

### 9.2 更新后的完整 Story Pack 文件清单(在 §3 的 11 文件基础上 +新增/扩展)

```
config/stories/<story_id>/
├── meta.yaml              # simulation_id / timeline / 初始 node / game_config / 玩家
├── story_graph.yaml       # ★核心 DAG: nodes + edges;node 内补 agent_behaviors{}
├── places.yaml            # 地点表;☆补 coverage[]
├── place_behaviors.yaml   # ★新增:behavior_hint 初值 + mutations 库
├── agents.yaml            # 角色表 + roles{} + factions{};☆补 capabilities[]/soul/goal/state
├── relations.yaml         # ★新增:初始关系网（运行期变化由通用引擎驱动）
├── groups.yaml            # 群组/阵营（动态成员走 timed_events.group_action）
├── signals.yaml           # story_advance 白名单 + keyword_sets + intent_heuristics
├── tools.yaml             # ★新增(可选):通用工具描述
├── endings.yaml           # 结局决策表 + bad_end
├── judges.yaml            # 裁判维度 + tech_keywords + LLM prompt 模板
├── timed_events.yaml      # ★实现:Turn N 广播/激活/inject + group_action + capability_grant/revoke
├── memory.yaml            # ★新增(可选):compressor 策略 + initial_memories
├── perception.yaml        # ★新增(可选):per-agent per-modality 过滤
├── language_style.yaml    # 禁用术语 / 大白话 / forbidden_actions
├── ui_text.yaml           # 前端可见子集（随 session 下发）
├── prompts/               # ★迁入:agent 人设 overlay + knowledge（含 initial_memory）
└── assets/                # 背景图 / 头像
```

> 一句话:补齐后,**world.db 的每张表(place/coverage/capability/relation/group/agent_location/segment)都有明确的 Story Pack 配置来源**,真正做到"改 config 换世界"。端到端设计与运行流程见 dev_logs/44。

---

**关键文件索引(绝对路径)**
- 借鉴源:`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/agents/story_graph.py`(StoryGraph 直接抄)、`agents/schemas.py`(nodes/edges schema)、`game_engine/scenes.py`(`load_line()` dispatch L215-303)、`game_engine/state.py`(GameState `[IF]` 求值)。
- 改造目标:`/Users/dawson/Documents/GitHub/demo/agent_world/hbm_demo/features/f05_story_routing/routing.py`(`apply_routing` L338、`resolve_ending_id` L252、`node_*_applies` L155-183、`build_inject_payload` L89)、`agent_signals.py`(`detect_node_a/b/c` L94-162、`detect_bad_end` L223)、`story_signals.py`(`VALID_STORY_SIGNALS` L7)、`core/runner/hbm_agent.py`(`_hbm_short_action_rules` L233)、`features/f04_stats/scoring.py`(L43/L69)、`features/f07_agent_control/pick_active.py`(`_primary_ids` L42)。
- 设计依据:`/Users/dawson/Documents/GitHub/demo/dev_logs/40_HBM_Demo_剧情与框架解耦_换剧本要改哪里.md`、`/Users/dawson/Documents/GitHub/demo/dev_logs/41_HBM_Demo_参考AI4VisualNovel_剧情数据驱动化.md`。
