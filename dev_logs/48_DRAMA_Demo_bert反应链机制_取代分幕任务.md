# 48 · Drama Demo · bert 反应链机制（取代分幕/任务链/张力）

## 1. 为什么

旧剧情结构是「分幕/节点 DAG + 任务链 + 张力弧」：管理 agent 生成一张故事图（nodes/edges/endings），
运行期 LLM 导演读「当前幕 + 出边 condition」判是否推进，并维护 0–100 张力值。问题：

- 玩家被「一幕一幕」推着走，自由交互被节点白名单忽略，体验是 railroad。
- 「幕/phase/张力」是套在世界之上的**虚拟概念**，玩家感知不到、也不该感知。

用户要的是更简单、更贴「活世界」的机制——**bert（条件→反应）**：

> 一个场景里有个罪犯不想被发现；但当玩家**主动逼问**是不是他干的，他**顶不住压力向玩家坦白**。

即「固定的玩家行为 → 触发特定 NPC 反应」，多条串成反应链。**不要任务、彻底去掉 phase、砍掉张力。
结局做成特殊的 bert。属性数值面板保留。**

## 2. 数据结构

一条 **bert** = `{id, trigger, target, reaction, place?, once?, arms?, requires?, ending?}`：

- `trigger`：自然语言写的**玩家条件**（玩家做/说了什么）。运行期由 LLM 导演读对话判命中，不靠关键词。
- `target` / `reaction`：命中后，哪个 NPC（agent_id）演什么反应。
- `requires` / `arms`：把 bert 串成**反应链**——`requires` 为空者开局即「上膛」；某 bert 触发后，
  它 `arms` 的、或 `requires` 已满足的后续 bert 才上膛。`once` 默认 true（触发一次即退出）。
- `ending` 非空 = **结局 bert**：`{kind: good|neutral|bad, summary}`，触发即收场（不需要 target/reaction）。

落点 `shared/story_pack/bert.py`（纯数据/算法，D3 不依赖 features）：`Bert` / `BertSet`，
`BertSet.armed_ids(fired)` 算当前上膛集合，`validate()` 兜引用闭合/可达/至少一个结局/孤儿检测。

## 3. 三段式落地：设计期写 / 运行期触发注入 / 反应链

### 设计期（生成）
- 新管理 agent **Bert 设计师**（`tools/story_studio/agents/bert_designer.py`）：`brief + cast → berts`
  （system 提示直接拿「罪犯受压坦白」当范例教它写反应链；符合「只教管理 agent、引擎不写硬规则」）。
- 接入 `orchestrator.generate_full`：在 cast 已定后（与 onboarding/acting_guide/stats 同属
  `critic_rounds>0` 生产路径的附加产物），生成 + 自校验 + 写 `berts.yaml`。离线 fake 门禁
  (`critic_rounds=0`) 跳过它 → 20 个 story_studio 单测与计费计数零改动。
- `BERT_OUTPUT_SCHEMA`（`authoring_schemas.py`）做生成期 schema 校验。

### 运行期（触发 + 注入）
- **Bert 导演** `director.judge_bert_triggers(armed, transcript)`（取代 `judge_transition`）：
  读「已上膛 bert 的玩家条件 + 最近对话」，判玩家是否命中某条 → 返回 `triggered` id 或 None。全 LLM，无硬规则。
- `interpreter_routing.route_story`（重写）：玩家有新发言时判一次 → 命中则
  ① `fired_berts += bid`；② 结局 bert → 写 `hbm.ending_id/ending_summary/ending_kind`，交还 watcher 收尾；
  ③ 普通 bert → `hbm.bert_reactions[target] = reaction`，并把 target 聚到反应该发生的地点。
- **注入**：`knowledge.py` 在为 target 组装 L4 知识时，读 `hbm.bert_reactions[target]` 注入
  「你现在的反应（剧情已触发，照这个演）」。走玩家直接对话的 inject 路径（真 session 携带 reaction），
  自然有「玩家施压 → 下一拍 NPC 破防」的一拍延迟。

### 反应链
`fired_berts` 驱动 `armed_ids`：A 触发后 A.arms / requires=[A] 的 B 才上膛，玩家下一句才可能触发 B——
一句话不会连环击穿，节奏天然。

## 4. 删除清单（phase / 任务 / 张力 = 虚拟概念，去掉）

- `DramaSession`：删 `tension`、`current_node_id`、`node_entered_tick`；`phase` 降级为**惰性空串**
  （f02/f07/f11 的 tick 解析等内部 plumbing 仍引用它，无测试时全删风险大，故保留为 `""`、不再由剧情驱动/不展示）；
  新增 `fired_berts` / `bert_reactions` / `ending_summary` / `ending_kind`。
- 读模型：`f01 lifecycle 快照` / `f14 delta` 去 `tension`；f14 结局信息改读 hbm（回退 graph.endings 兼容旧包）。
- `setup_scene_for_node` → 空操作（NPC 由 agents.yaml 各就各位，世界自然运行）；`route_story` 不再发
  「新任务/phase_route」横幅。
- 前端：删 phase 显示（手机面板「当前任务」/StatusPanel「当前幕」）、张力 HUD/柱状图、phaseToast/
  toastedPhases/DISMISS_PHASE_TOAST、`constants/phaseTransitions.ts`、废弃的 `PhaseToast.tsx`。

## 5. story_graph 已彻底退役（第二阶段）

`phase` 与 `story_graph` 两个遗留概念已**彻底删除**（用户验收阶段要求）：

- **删 phase**：`DramaSession.phase` 与 f02/f07/f11/f03/f14 等约 22 个文件里所有 phase 传参/读写全删
  （phase 早已是 vestigial——`resolve_llm_params`/`resolve_inject_tick_count`/`resolve_loop_min_ticks` 都忽略它，
  删除零行为变化）。仅 trace（f15/f06）按调试保留、收值 None。
- **删 story_graph**：退役 Designer / Writer（agent）/ `generate` / `regenerate_writer` / story_graph.yaml。
  - 生成流水线改为 **Casting(brief) → Bert 设计师(brief+cast→berts) → assemble → validate(X+B) → Critic(brief,casting,berts)**。
  - `StoryGraph.empty()` + loader 缺文件返回空图 + `validate()` 空图直接合法；`list_story_ids` 改按 **berts.yaml**（兼容旧 story_graph.yaml）发现包。
  - Critic rubric 改评 bert（trigger 可判定/reaction 贴人设/反应链连贯/结局分量）；onboarding 不再依赖节点。
- 无 `berts.yaml`（旧任务包/空包）→ `route_story` 直接返回，世界照常运行，只是没有脚本化反应（向后兼容降级）。

## 6. 验证状态（截至本 dev_log）

- **离线**：bert 模型（链 + 结局 + 坏例 + 整数 id 容错）、Bert 设计师端到端、`route_story` 状态机
  （confess→beg 链 + good_end 结局）、新 bert 生成流水线（fake，落 berts.yaml 不落 story_graph）、
  全栈 import、story_studio 门禁 **16/16**——全绿。
- **真 LLM**：`test_create_acceptance.py`（用户给一段剧情 → Casting+Bert 设计师 生成 17 条 bert/3 结局的完整可玩包）通过；
  全流程游玩 E2E（生成→起 Runner+Flask→驱动 HTTP 玩→bert 触发）见 `scripts/ops/bert_play_e2e.py`。
- **运行期游玩 E2E**（`scripts/ops/bert_play_e2e.py`：真生成→起 Runner+Flask→curl 驱 HTTP 玩→验 bert 触发）。
- **E2E 暴露并修掉的真 bug**（多为「校验比运行期更严」或「退役后遗留的硬假设」）：
  1. Bert 设计师 LLM 偶尔把 id/arms/requires 输出成整数、把 place/reaction/target 输出成 null →
     schema 放宽成 `string|integer|null`、`Bert.from_mapping` 统一 `str()`/`_as_int` 归一化。
  2. `[B8]` 可达性只跟 `arms` 漏了 `requires`，误杀「仅经 requires 可达」的合法结局 → 改为与运行期
     `armed_ids` 一致的不动点（requires 与 arms 同为前置边）。
  3. Casting 偶尔把已死受害者列成 agent（空 inner 撞 minLength）→ 提示「只列活着、能演的角色」。
  4. **退役 node 后玩家可能独自空房** → 旧 `handle_player_turn` 在「无同处 NPC」时硬 `RuntimeError`(503)。
     bert 世界里玩家对空房说话其台词仍应记进 f2f 供导演判触发：世界循环模式下不再硬失败；
     `setup_scene_for_node` 改为开局把「开局上膛」bert 的 target 聚到玩家面前（开场戏）。
