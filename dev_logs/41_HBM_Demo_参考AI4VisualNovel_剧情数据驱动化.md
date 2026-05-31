# 参考 AI4VisualNovel：可借鉴之处 + 如何做到「改剧情不碰硬代码也能跑 phase」

> 由多智能体工作流并行精读 AI4VisualNovel 源码(4 区 + 综合)生成。配套 dev_logs/40。


> 面向 HBM 谈判 demo 团队。本文对照 `AI4VisualNovel/` 源码（`agents/story_graph.py`、`agents/schemas.py`、`game_engine/{data,scenes,state,manager}.py`、`export_renpy.py`）与我们 `agent_world/hbm_demo/` 现状（`features/f05_story_routing/routing.py`、`agent_signals.py`、`core/runner/hbm_agent.py`、`features/f04_stats/scoring.py`）以及 `dev_logs/40` 的 Story Pack 方向，给出可执行的借鉴清单与最小改造伪代码。

---

## 1. AI4VisualNovel 架构速览

AI4VN 把「从一句话需求 → 可玩视觉小说」拆成四块，彼此通过**纯数据契约**衔接，没有任何一块写死了具体故事：

### 1.1 多智能体 Studio 管线（生成期，离线）
`WorkflowController` 编排一条「制片人审核 → 编剧切片 → 演员表演 → 画师出图」的流水线，分三个 phase：

- **`run_design_phase()`**：`DesignerAgent.generate_game_outline()` 先产出宏观大纲（文本分组 `groups[]`），`ProducerAgent.critique_game_outline()` 审核 → 不过则带 feedback 重生成；通过后 `DesignerAgent.generate_story_graph_from_outline()` 把大纲落成 DAG，`ProducerAgent.critique_story_graph()` 用 **ReAct + 工具调用**（`graph_validate`、`enumerate_paths`）做结构校验。两层 Plan-Review-Revise。
- **`run_script_phase()`**：`WriterAgent.split_node_into_plots()` 把节点摘要切成片段 → `decide_next_speaker()` 决定谁说话 → `ActorAgent.perform_plot()` 让每个角色按自己的人设说一句 → `synthesize_script()` 整合成带 `<image>`/`<choice>` 标签的剧本文本。
- **`run_render_phase()`**：`ArtistAgent` 按 `scenes[]`/`characters[]`/表情库生成背景与多表情立绘（链式参考图 + 反馈迭代）。

关键点：管线本身**不认识任何具体角色或剧情**，它只认 schema。换故事 = 喂不同的需求文本，重跑管线。

### 1.2 DAG 剧情图数据模型（生成期的产物 = 运行期的输入）
核心是 `agents/schemas.py` 里两个 schema：

- `GAME_OUTLINE_SCHEMA`：`title / background / art_style / story_outline.groups[] / characters[] / scenes[]`。`groups` 是**粗粒度文本规划层**（"开场建立 / 中段分支 / 终局"），不承诺节点数。
- `STORY_GRAPH_SCHEMA`：`nodes{}`（每个 `{id, summary, type}`，`type ∈ {normal, merge}`）+ `edges[]`（每条 `{from, to, choice_text}`，`choice_text=null` 表示自然推进，非 null 表示玩家选项）。硬约束：必有 `root`、无环、全可达。

`agents/story_graph.py` 的 `StoryGraph` 把这堆数据封成图对象：`topological_sort()`（遍历顺序）、`get_children()`（下一步分支）、`get_parents()`（汇合点上文）、`is_merge_point()`、`validate()`、`enumerate_all_paths()`、`get_reachable_endings()`。**整条流向由邻接表算出，没有一句 `if`。**

### 1.3 数据驱动引擎（运行期，Pygame）
`game_engine/` 是一台「读 JSON+标签脚本就跑」的解释器，完全不含故事逻辑：

- `data.py StoryParser`：把 `<scene>`、`<image id="">`、`<content id="">`、`<choice target="">`、`<jump target="">`、`[IF: Role >= Level]` 这套标签语言解析成 `{node_id: [指令字典...]}`。
- `state.py GameState`：运行时容器，只管 `current_node_id`、`story_flags[]`、`characters{met, story_flags}`、`choices_made[]`。`add_story_flag()` 改状态。
- `scenes.py DialogueScene.load_line()`：**逐行 dispatch 的解释器核心**——按 `line_type` 分发（`scene`→换背景、`image`→换立绘、`dialogue`→打字机、`choice_option`→建按钮、`jump`→`self.manager.game_state.current_node_id = target`、`if`→查 `story_flags`）。这就是一台标签驱动的状态机。
- `manager.py GameManager`：无脑驱动器，`current_node_id = "root"` 起步，按 node 取指令列表给 `DialogueScene` 执行。

### 1.4 RenPy 导出（多引擎解耦）
`export_renpy.py convert_to_renpy()` 把 `game_design.json + story.txt` 编译成 `script.rpy`：`characters[]`→`Character()`、`scenes[]`→背景定义、`<content>`→角色台词、`<choice>`→`menu`、`<jump>`→`jump label`。证明了**中间格式（标签脚本）独立于具体引擎**，同一份数据可落 Pygame 也可落 RenPy。

---

## 2. 与我们 HBM demo 的共通之处（逐条对应）

我们和 AI4VN 在抽象层面高度同构，这是借鉴成立的前提：

| 维度 | AI4VisualNovel | HBM demo | 对应关系 |
| --- | --- | --- | --- |
| **多 agent** | 制片/编剧/演员/画师（生成期协作） | 7 个谈判 agent（运行期协作） | 都是「每 agent 一份 profile + 独立 LLM 调用」 |
| **角色扮演 / 人设一致** | `ActorAgent(character_info)`，`personality/background` 注入 system prompt | `hbm_scenario.yaml` 的 `agents[].soul/long_term_goal`，`agent_*.yaml` overlay | 都靠「角色卡 → prompt 模板」保证行为一致 |
| **场景 / 地点** | `scenes[]`（`id/name/description`）+ 背景图 | `places[]`（4 地点 + `behavior_hint` + 背景图） | 一一对应；我们还多了 agent 在 place 间移动 |
| **对话单元** | `plot_segment`（演员逐句表演） | 每个 player turn 的 F2F/RDC/群聊消息 | 都是「片段化的对白原子」 |
| **分支 / 选择** | `edges[].choice_text` | 玩家自由输入 → `story_advance` 信号 / RDC 链触发 node | 都是「在某节点做选择 → 跳到下一节点」 |
| **汇合** | `type: merge` 节点（多父） | Phase 2 的 A 线/B 线最终汇到 Phase 3 | 都需要 merge 语义 |
| **立绘 / 背景** | 多表情立绘 + 场景背景 | 前端 `storyAssets.ts` 的 `PLACE_BACKGROUNDS` + `agent_{id}.png` 头像 | 资产都来自 `places[]`/`agents[]` 数据 |
| **结局** | 叶子节点（`get_reachable_endings`） | `ending_join_nvidia / seed_round / cold_deal / bad_reject` | 都是「路径终点 = 结局」 |
| **裁判 / 评估** | `ProducerAgent` 审核 DAG 合法性 | `f04_stats/scoring.py` 四维打分 + Phase4 LLM 裁判 | 都用 LLM 做结构化判定 |

**结论：抽象层我们几乎是同一套对象（角色、地点、节点、边、选择、汇合、结局、裁判）。差异不在"概念缺失"，而在"我们把这些概念写成了 Python 控制流，它写成了数据"。**

---

## 3. 关键差异：为什么它改剧情不改代码，我们不能

差异可以一句话概括：**AI4VN 的"故事流向"是数据（DAG + 标签脚本），由一台通用解释器消费；我们的"故事流向"是控制流（`if phase == "Phase X"` + `detect_node_*` 函数 + `if trust >= 25`），写死在引擎里。** 落到三个具体机制：

### 3.1 数据 schema vs `if` 链 —— 流向的表达方式
AI4VN 表达「Phase 1 完成后进 Phase 2，Jensen 进私室」会写成 `edges` 上的一条数据 + node 的 summary。我们的 `routing.py:apply_routing()`（L338-443）是这样：

```python
if node_a_applies(session, db=db, current_tick=current_tick):
    send_move_agent(ipc_client, agent_id=JENSEN_ID, place_id=PLACE_JENSEN_ROOM, ...)
    sync_player_place_on_routing(session, new_phase="Phase 2", node="A", ...)
    session.phase2_start_tick = current_tick
    ...
if node_b_applies(...):  # Jensen→PLACE_NEGOTIATION + place_mutation + Phase 3
    ...
if node_c_applies(...):  # CEO_IDS→PLACE_RECEPTION + Phase 4
    ...
```

这里 `JENSEN_ID=2`、`PLACE_JENSEN_ROOM`、`"Phase 2"`、节点 A/B/C 的"检测→搬人→转 phase"全部是 Python 字面量和函数。换故事，这三个 `if` 块每一行都要改。**它的 `node_a/b/c` 在 AI4VN 里就是 `edges` 数组的三行 JSON。**

同理 `agent_signals.py:detect_node_a/b/c()` 把"前台(1)→Jensen(2)→VP(3) 的 RDC 链 + approval 关键词"写成了三个独立函数；AI4VN 这种"满足条件就转移"的逻辑全在 `StoryGraph.get_children()` 的邻接表里，一个解释器吃掉。

### 3.2 解释器引擎 vs 写死控制流 —— 谁来消费流向
AI4VN 的 `DialogueScene.load_line()` 是**一个 dispatch 表**：来什么指令做什么，引擎不知道"这是哪个故事"。我们没有这一层——路由逻辑直接焊在业务函数里（`build_inject_payload` L123 写死 `player_turn == 16 and phase == "Phase 3"`；`resolve_ending_id` L252-257 写死 `trust >= 25`）。**他们有"解释器 + 数据"，我们只有"被解释的内容固化进了解释器自身"。**

### 3.3 状态/变量系统 vs 散落的常量
AI4VN 用 `GameState.story_flags[]` + `[IF: Role >= Level]` 做条件分支——所有"是否解锁"都是查 flag 表。我们的状态散在 `session.phase`、`session.phase2_start_tick`、`trust` 整数里，分支逻辑用 `if` 直接读这些字段。没有统一的"变量空间 + 条件求值器"，所以每加一个分支就得加一段 `if`。

### 3.4 它还多了一个我们没有的东西：生成期与运行期分离
AI4VN 是**离线生成 → 运行**：`story.txt` 一旦生成就是确定的，运行期只回放。我们是**实时多 agent**：每个 turn 的对话是当场 LLM 生成的，"下一步去哪"取决于 agent 当场说了什么。所以我们不能照搬"预先枚举所有路径再回放"，但**"流向用 DAG 表达 + 解释器消费"这一层完全可以搬**——区别只是我们的边触发条件是"实时检测 RDC/信号"而非"玩家点了哪个按钮"。

---

## 4. 最值得借鉴的设计（具体到字段/类/函数）

### 4.1 `STORY_GRAPH_SCHEMA` 的 nodes/edges 数据结构 ★最高优先级
直接把它的形状搬进我们的 Story Pack。映射：

- `nodes{id, summary, type}` → 我们的 Phase/节点。`type: merge` 正好表达 Phase 2 的 A/B 线汇合。
- `edges{from, to, choice_text}` → 我们的 node 转移。差异：我们的 `choice_text` 不是"玩家点的按钮文案"，而是**触发条件**（story_signal / RDC 链 / 关键词）。所以我们要把 `choice_text` 扩展成 `trigger`（见 §5）。

**用得上**：`routing.py` 的三个 `node_*_applies` + `apply_routing` 全部退化成"遍历 edges，谁的 trigger 命中就执行谁的 actions"。

### 4.2 `StoryGraph` 类的方法集 ★
- `topological_sort()` → 校验我们的 phase 图无环、给出推进顺序。
- `get_children(current_node)` → 当前节点的所有出边（= 当前能触发哪些转移），替代 `PHASE_INJECT_AGENTS` 的查表。
- `is_merge_point()` → 判断是否是汇合点（A/B 线合流），决定上文如何拼。
- `validate()` + `get_reachable_endings()` → **加载 Story Pack 时就校验**："所有结局可达吗？有没有死路（非终点却无出边）?" 这正是我们现在缺的——`dev_logs/40` §3.3 提到结局判定要从 if 链升格为决策表，`validate` 是它的质量门禁。
- `enumerate_all_paths()` → 自动跑出所有谈判路线，回归测试时断言"join/seed/cold/bad 四条路径都存在"。

**用得上**：新建 `shared/story_graph.py`，几乎可直接拷贝 `AI4VisualNovel/agents/story_graph.py`，只把 `choice_text` 的语义改成"trigger 引用"。

### 4.3 `GameState` + `[IF: Role >= Level]` 变量/条件系统 ★
它的 `story_flags[]` + `[IF]` 求值是我们做"结局判定"和"条件分支"的现成模型。我们的 `trust >= 25` 本质就是 `[IF: trust >= 25]`。把结局条件写成数据：

```yaml
endings:
  - { id: ending_join_nvidia, when: "intent == join_nvidia and trust >= 25" }
  - { id: ending_seed_round,  when: "intent == seed_round and trust >= 15" }
  - { id: ending_cold_deal,   when: "true" }   # 兜底
```

用一个小的安全表达式求值器（白名单变量 `trust/intent/phase/flags`）替代 `resolve_ending_id` 的 if 链。

### 4.4 `DialogueScene.load_line()` 的 dispatch 模式 ★
这是替代 `apply_routing` 的样板：**一个 `{action_type: handler}` 注册表**。我们的 `actions` 有三种原语（`agent_moves` / `place_mutations` / `state_updates`），正好对应它的 `scene`/`image`/`jump` 三种 dispatch 分支。照着写一个 `apply_actions(actions, ctx)` 即可。

### 4.5 `ActorAgent` 的人设一致机制
我们已经有 `agents[].soul` + overlay，这块对齐度最高。可借鉴的增量：它的 `_build_system_prompt()` 是**纯模板渲染**（character_info 字段填进模板），而我们的 `hbm_agent.py:_hbm_short_action_rules()`（240+ 行 agent×phase 行为矩阵）是手写 `if aid == 1 and phase == "Phase 1"`。应学它把行为卡做成数据（`agent_phase_behaviors[(aid, phase)]` → 模板拼装），见 `dev_logs/40` §3.1 对该函数的拆解建议。

### 4.6 RenPy 导出的映射表思路
短期我们不需要导 RenPy，但它的 `convert_to_renpy()` 证明了一件事：**只要中间格式是数据（标签脚本/DAG），就能再编译到任意目标**。对我们的价值是反向的——把"前端可见子集"（角色名/地点/结局文案/幕过渡）当成一个**可下发的编译产物**（`dev_logs/40` §6.2 的 `ui_text.yaml`），后端在 session 初始化时下发，前端 `constants/*` 改成运行时注入。这就是"导出映射"思路用在前端解耦上。

---

## 5. 重点：把 Phase/路由/结局做成数据驱动该怎么设计

借 AI4VN 的「DAG + 解释器」，落到我们的 Story Pack。下面给出 schema 与一个**通用状态机解释器**替代 `routing.py` 的 if 链。

### 5.1 phase 图 schema（`config/stories/<id>/story_graph.yaml`）
把 Phase 升格为图节点，node 转换升格为带 trigger 的边。复用 `STORY_GRAPH_SCHEMA` 的 `nodes/edges` 骨架，扩展两处：边上 `choice_text` → `trigger`（触发条件），新增 `actions`（命中后的副作用）。

```yaml
nodes:
  root:    { id: root,    phase: "Phase 1", type: normal }   # 起点
  phase2:  { id: phase2,  phase: "Phase 2", type: normal }
  phase3:  { id: phase3,  phase: "Phase 3", type: merge  }   # A/B 线汇合
  phase4:  { id: phase4,  phase: "Phase 4", type: normal }
  end:     { id: end,     phase: "Phase 4", type: ending }   # 叶子=结局判定点

edges:
  # 原 node_a：Phase1→Phase2，检测前台→Jensen→VP 的 RDC 链或 approve 信号
  - from: root
    to: phase2
    trigger:                       # ← 取代 AI4VN 的 choice_text
      any_of:
        - { type: story_signal, signal: approve_visitor }
        - { type: rdc_chain, chain: [[1,2],[2,3]],
            approval: { sender: 2, recipient: 1, keywords_ref: approve_keywords } }
    actions:                       # ← 取代 apply_routing 里 send_move_agent 那段
      agent_moves:   [{ agent_role: leader, dest: jensen_private_room }]
      state_updates: { phase2_start_tick: "$current_tick" }
  # 原 node_b：Phase2→Phase3 + place_mutation
  - from: phase2
    to: phase3
    trigger:
      rdc_positive: { sender_role: tech_vp, recipient_role: leader,
                      keywords_ref: tech_vp_approval_keywords }
    actions:
      agent_moves:     [{ agent_role: leader, dest: negotiation_room }]
      place_mutations: [{ place: negotiation_room, behavior_hint_ref: node_b_hint }]
      state_updates:   { phase3_start_tick: "$current_tick" }
  # 原 node_c：Phase3→Phase4
  - from: phase3
    to: phase4
    trigger:
      rdc_expel: { sender_role: leader, recipients_role: suppliers, keywords_ref: expel_keywords }
    actions:
      agent_moves: [{ agents_role: suppliers, dest: nvidia_reception }]
```

### 5.2 结局判定 schema（`endings.yaml`）—— 决策表替代 if 链
```yaml
endings:
  # signal 覆盖优先（取代 resolve_turn25_ending 的 offer_* 分支）
  - { id: ending_join_nvidia, override_signal: offer_join, priority: 10 }
  - { id: ending_seed_round,  override_signal: offer_seed, priority: 10 }
  # 否则按表达式（取代 resolve_ending_id 的 trust 阈值 if）
  - { id: ending_join_nvidia, when: "intent == 'join_nvidia' and trust >= 25", priority: 5 }
  - { id: ending_seed_round,  when: "intent == 'seed_round'  and trust >= 15", priority: 5 }
  - { id: ending_cold_deal,   when: "true", priority: 0 }     # 兜底
bad_end:
  id: bad_reject
  status: game_over
  conditions:                       # 取代 detect_bad_end()
    - { type: story_signal, signal: reject_visitor }
    - { type: phase_timeout, phase: "Phase 1", max_turns: 10 }
```

### 5.3 通用状态机解释器（替代 `routing.py` 的 `apply_routing` + `node_*_applies`）

核心是两段：**`detect(trigger)`**（解释触发条件）和 **`apply(actions)`**（解释副作用），各做一个 dispatch 表。下面是最小改造伪代码：

```python
# shared/story_graph.py —— 借自 AI4VisualNovel/agents/story_graph.py，几乎照抄
class StoryGraph:
    def __init__(self, data): ...        # 复用：nodes/edges/adjacency/reverse_adjacency
    def get_children(self, node_id): ...  # 复用
    def is_merge_point(self, node_id): ...# 复用
    def validate(self): ...               # 复用：加载期校验无环 + root 存在
    def get_reachable_endings(self, n): ...# 复用：校验结局可达

# features/f05_story_routing/interpreter.py —— 新的通用解释器
TRIGGER_HANDLERS = {           # ← dispatch 表，模仿 DialogueScene.load_line 的分发
    "story_signal": lambda t, ctx: has_story_signal(ctx.db, t["signal"], **ctx.window),
    "rdc_chain":    lambda t, ctx: _rdc_chain_matched(ctx.db, t, ctx),
    "rdc_positive": lambda t, ctx: _rdc_positive(ctx.db, t, ctx),
    "rdc_expel":    lambda t, ctx: _rdc_expel(ctx.db, t, ctx),
    "phase_timeout":lambda t, ctx: ctx.session.player_turn - ctx.phase_start_turn(t["phase"]) >= t["max_turns"],
}
def detect(trigger, ctx) -> bool:
    if "any_of" in trigger:
        return any(detect(sub, ctx) for sub in trigger["any_of"])
    (kind, spec), = trigger.items()          # 单键 trigger
    return TRIGGER_HANDLERS[kind](spec, ctx)

ACTION_HANDLERS = {            # ← 取代 apply_routing 里手写的 send_move_agent 序列
    "agent_moves":     lambda spec, ctx: [ctx.move(ctx.role_to_id(m), m["dest"]) for m in spec],
    "place_mutations": lambda spec, ctx: [ctx.mutate_place(m) for m in spec],
    "state_updates":   lambda spec, ctx: ctx.session.update(_resolve_vars(spec, ctx)),
}
def apply(actions, ctx):
    for kind, spec in actions.items():
        ACTION_HANDLERS[kind](spec, ctx)

# 这就是新的 apply_routing —— 表驱动，零 if 链、零硬编码 place/agent
def apply_routing(session, *, ipc_client, db, current_tick, **kw):
    story = load_story_graph(session.story_id)       # 读 story_graph.yaml
    ctx = RoutingCtx(session, db, ipc_client, current_tick)
    applied = {"nodes": []}
    for child_id, edge in story.get_children(session.current_node_id):  # 借 AI4VN 邻接表
        if detect(edge["trigger"], ctx):
            apply(edge.get("actions", {}), ctx)
            session.current_node_id = child_id
            session.phase = story.get_node(child_id)["phase"]           # phase 也来自数据
            applied["nodes"].append(child_id)
            break        # 一个 turn 推进一步
    return applied

# 结局判定 —— 决策表替代 resolve_ending_id/resolve_turn25_ending
def resolve_ending(session, db, *, since_t, t_now):
    spec = load_endings(session.story_id)
    for rule in sorted(spec["endings"], key=lambda r: -r["priority"]):
        if "override_signal" in rule and has_story_signal(db, rule["override_signal"], since_t=since_t, t_now=t_now):
            return rule["id"]
        if "when" in rule and safe_eval(rule["when"], session.vars()):  # [IF] 求值器
            return rule["id"]
    return spec["fallback"]
```

要点：
- `session.phase` 不再是写死的字符串比较对象，而是 `story.get_node(current_node_id)["phase"]` 读出来——**Phase 升格为数据**，从而支持 3 幕/6 幕/非线性。
- `role_to_id` 把 `leader/suppliers` 等**角色名**映射到 agent id（查 `agents.yaml` 的 `roles`），消除 `JENSEN_ID=2`、`CEO_IDS=(4,5,6)` 这类编号硬编码。
- `safe_eval` 是受限表达式求值器（变量白名单 `trust/intent/phase/flags`），对应 AI4VN 的 `[IF: Role >= Level]`。
- `agent_signals.py` 的 `detect_node_a/b/c` 三个函数合并进 `TRIGGER_HANDLERS` 的 `rdc_chain` 一个 handler，关键词全部经 `keywords_ref` 解引用 `signals.yaml`。

这套解释器跑现有 HBM 的 `story_graph.yaml` 应当**逐帧等价**于今天的 if 链（这是阶段二的回归判据）；跑一个新故事的 `story_graph.yaml` 则零代码改动。

---

## 6. 直接可抄 / 需要适配 / 不适用

### 直接可抄（拿来就用，改名即可）
- **`agents/story_graph.py StoryGraph`**：`topological_sort/get_children/get_parents/is_merge_point/validate/get_reachable_endings/enumerate_all_paths` 全部可拷进 `shared/story_graph.py`。
- **`agents/schemas.py` 的 nodes/edges 骨架**：`STORY_GRAPH_SCHEMA` 直接作为我们 `story_graph.yaml` 的 JSON Schema 校验基础（加 `jsonschema` 依赖，AI4VN 的 `requirements.txt` 也用它）。
- **`DialogueScene.load_line()` 的 dispatch 表模式**：作为 `apply_routing` 的解释器样板。
- **`GameState.story_flags[]` + `[IF]` 条件求值**：作为结局/分支判定的变量系统模型。
- **加载期 `validate()` 质量门禁**：作为 Story Pack 的"无环 + 结局可达 + 无死路"校验。

### 需要适配（思路对，语义要换）
- **`edges[].choice_text` → `trigger`**：它是"玩家点的按钮"，我们是"实时检测 RDC/信号/关键词"。语义从"被动选择"变"主动检测"。
- **`topological_sort` 的用途**：它用来排"生成脚本的顺序"，我们用来"校验图合法 + 推进顺序"。运行期我们不预先遍历全图，而是每 turn 从 `current_node_id` 取出边。
- **`ProducerAgent` 的 ReAct 审核**：可适配成"加载 Story Pack 时跑 `graph_validate`/`enumerate_paths`"的 CI 检查，但不必引入 LLM——纯算法校验即可。
- **`ui_text` 下发**：借 RenPy 导出的"映射编译"思路，但目标是前端 `constants/*` 而非 `.rpy`（见 `dev_logs/40` §6.2 `ui_text.yaml` + L150 下发机制）。
- **`agent_phase_behaviors` 模板化**：借 `ActorAgent._build_system_prompt()` 的纯模板渲染，替代 `hbm_agent.py:_hbm_short_action_rules()` 的 240 行 if 矩阵。

### 不适用（我们是实时多 agent，它是离线生成 VN）
- **整条 Studio 生成管线（Designer/Writer/Actor/Artist 离线出 story.txt）**：我们的对白是运行期实时 LLM 生成，不预生成完整剧本。`run_script_phase()` 那套"切片→表演→合成"的离线流程不搬。
- **`enumerate_all_paths` 预枚举所有结局并回放**：我们的路径由玩家实时输入决定，不能预生成。但可用于**测试期**枚举校验。
- **`StoryParser` 的标签脚本作为运行时主数据流**：AI4VN 运行期靠回放 `story.txt`；我们运行期靠 IPC + 实时 inject。标签脚本对我们更多是"可选导出格式"而非运行核心。
- **链式参考图 + 表情库迭代（`ArtistAgent`）**：我们前端用固定立绘/头像，不需要多轮 AIGC 立绘生成（虽然本分支 `aigc-realtime-render` 在做实时出图，但那是另一条线，不依赖这套）。
- **`is_protagonist` 单主角假设**：我们玩家 = agent 0 的外来访客模型与它不同，属 `dev_logs/40` §4 第三层框架议题。

---

## 7. 落地建议：AI4VisualNovel 能加速 `dev_logs/40` 的哪几步

`dev_logs/40` 已规划四个阶段。AI4VN 的现成代码能直接压缩其中的**阶段二与阶段三**——这两个阶段恰是"把 if 链改成解释器"的硬骨头，而 AI4VN 已经把解释器写好了。

**阶段一（抽字符串与映射）** —— AI4VN 帮助有限。
这一阶段是平移 `_AGENT_NAMES`/`PLACE_LABELS`/`tech_keywords` 等纯值，主要是体力活。可借的只有 `GAME_OUTLINE_SCHEMA` 的 `characters[]`/`scenes[]` 字段形状作为 `agents.yaml`/`places.yaml` 的 schema 参考。

**阶段二（抽 Phase/路由/信号为数据驱动）** —— ★AI4VN 最大加速点。
- 直接拷 `StoryGraph` 到 `shared/story_graph.py`，省掉自研图结构+拓扑排序+校验。
- 照 `load_line()` 的 dispatch 模式写 `detect()`/`apply()`，把 `routing.py:apply_routing` + `node_*_applies` + `agent_signals.py:detect_node_*` 一次性表驱动化（§5.3 伪代码）。
- 用 `STORY_GRAPH_SCHEMA` + `jsonschema` 做 `story_graph.yaml` 校验，用 `validate()`/`get_reachable_endings()` 做加载期门禁。
- 回归判据可用 `enumerate_all_paths()` 自动断言"现有 HBM 四条路径仍存在"。
- 预计能省掉自研 DAG/解释器的设计与调试，是整条路线投入产出比最高的一步。

**阶段三（抽结局与裁判）** —— ★中等加速。
- 借 `GameState` 的 `story_flags[]` + `[IF]` 求值模型，把 `resolve_ending_id`/`resolve_turn25_ending` 改成 `endings.yaml` 决策表 + `safe_eval`（§5.2）。
- 三段 LLM 裁判 prompt（`classify_turn25_intent`/`classify_phase4_conclusion`/`scoring.py`）改成 `judges.yaml` 模板 `.format(**story_vars)`——这部分 AI4VN 没有直接对应，但 `ProducerAgent` 的"schema 约束 + 模板 system_prompt"是参照。

**阶段四（前端文案化）** —— 中等加速。
- 借 `export_renpy.py` 的"映射编译"思路实现 `ui_text` 下发：后端把 Story Pack 的前端可见子集编译成一份 JSON，session 初始化时随 `GET /scenario` 下发，前端 `constants/*`/`storyAssets.ts`/`EndingScreen.tsx` 改运行时注入。

**建议的最小验证闭环**：先在阶段二做出 `shared/story_graph.py`（抄 AI4VN）+ `interpreter.py`（§5.3），用现有 HBM 的 `story_graph.yaml` 喂解释器，跑回归确认与今天 if 链逐帧等价；再造一个"改地点名/角色名、Phase 数仍为 4"的**最小同构 demo 故事**，验证"只改 `config/stories/<id>/` 能跑通 Phase1→4 + Turn16 事件 + bad_end 三路径"。这一步绿了，"改剧情不碰硬代码也能跑 phase"对**同构故事**即告成立；异构故事（非线性幕/多玩家/可变属性维度）则进入 `dev_logs/40` §4 第三层框架改造的独立议题。

---

**关键文件索引（绝对路径）**
- 借鉴源：`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/agents/story_graph.py`（StoryGraph，直接可抄）、`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/agents/schemas.py`（nodes/edges schema）、`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/game_engine/scenes.py`（`load_line()` dispatch，L215-303）、`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/game_engine/data.py`（StoryParser 标签语言）、`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/game_engine/state.py`（GameState 变量系统）、`/Users/dawson/Documents/GitHub/demo/AI4VisualNovel/export_renpy.py`（映射编译）。
- 改造目标：`/Users/dawson/Documents/GitHub/demo/agent_world/hbm_demo/features/f05_story_routing/routing.py`（`apply_routing` if 链 L338-443、`resolve_ending_id` L252-257）、`/Users/dawson/Documents/GitHub/demo/agent_world/hbm_demo/features/f05_story_routing/agent_signals.py`（`detect_node_*`）、`/Users/dawson/Documents/GitHub/demo/agent_world/hbm_demo/core/runner/hbm_agent.py`（`_hbm_short_action_rules` 行为矩阵）、`/Users/dawson/Documents/GitHub/demo/agent_world/hbm_demo/features/f04_stats/scoring.py`（裁判 prompt）。
- 设计依据：`/Users/dawson/Documents/GitHub/demo/dev_logs/40_HBM_Demo_剧情与框架解耦_换剧本要改哪里.md`（Story Pack 目录结构 §6.1、各 schema §6.2、落地路线 §7）。
