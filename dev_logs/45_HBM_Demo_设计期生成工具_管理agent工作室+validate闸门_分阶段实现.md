> 由多智能体工作流(4 读者 grounding + 5 审计 + 2 综合)生成。配套 dev_logs/42(Story Pack schema)、43(管理 vs 演员)。借鉴 AI4VisualNovel 真实工作室(workflow.py + agents/*)，产出我们自己的 Story Pack schema。

# 设计期生成工具：管理 agent 工作室 + validate 闸门 — 分阶段实现

> 本章定义 hbm_demo「换故事只改 config」愿景里**设计期(authoring time)那一侧**：用户写一份半结构化 story brief，经过一条由若干「管理 agent」组成的离线工作室流水线，产出一整包符合 dev_logs/42 §3/§9 schema 的 Story Pack，再经一道确定性 validate 闸门把关，最后交用户审阅/微调。它**借鉴** AI4VisualNovel(下称 AI4VN)真实工作室的工程做法(契约先行、生成≠审核、有界重生成回路、幂等落盘、双层闸门),但**产出的是我们自己的 schema**,而非 AI4VN 的 `game_design.json`。
>
> 阅读前提：运行期解释器(`shared/story_graph.py` + `features/f05_story_routing/interpreter.py`)、Story Pack 文件契约(dev_logs/42 §3/§9)是本章的**下游消费方**。本章产出的所有 YAML 最终都要喂给它们,因此**必须先有干净的 Story Pack 格式 + 解释器,再做本工具**(见 §6 阶段对齐)。

---

## 1. 定位与边界

### 1.1 一句话定位

设计期生成工具(代号 **story_studio**,落点 `agent_world/hbm_demo/tools/story_studio/`)是一个**纯离线 CLI 工具**,把一份用户 story brief 编译成一整包 Story Pack(约 17 个 YAML + `prompts/` + `assets/`),落到 `config/stories/<story_id>/`。它是「编译器」,Story Pack 是「字节码」,运行期解释器是「虚拟机」。

### 1.2 硬边界(红线,违反即架构错误)

| 边界 | 规约 | 机制保证(非仅约定) |
|---|---|---|
| **绝不进 Flask 运行时** | story_studio 不被 `http/routes.py` 任何请求处理函数同步调用;`POST /scenario` 最多**触发**一个后台任务,真正 pipeline 跑在 Flask 请求周期之外,产物是文件 | gate 增红线测试:断言 `http/*` 的 import 图不含 `tools.story_studio` |
| **绝不进引擎/Runner** | 不进 `agent_world/world`、`agent_world/agents`、`kernel`、`core/runner/world_loop`;与 tick 推进正交 | 分层依赖红线测试(类比 test_m0 的 `test_r3`):断言 `tools.story_studio` 的 import 图**不含** `seed_world` / `WorldDB` / `build_kernel` / `kernel` |
| **只写 config,绝不碰 playthrough** | 输出根**固定**为 `config/stories/<id>/`;**禁止**写 `sim/<id>/world.db`(玩家存档) | (a) story_studio 只允许 import `shared.story_pack` 的「写 config」接口 + `StoryGraph.validate()`;(b) 运行期断言「输出路径不得在 `sim/` 下」;(c) `config/stories/<id>` 与 `sim/<id>` 物理分目录,authoring 对 `sim/` 无写权限;(d) gate 加红线测试断言 story_studio import 图不含 `seed_world`/`WorldDB` |
| **产出物 = Story Pack 整包** | 唯一交付物是 `config/stories/<id>/` 下的完整一包数据,无任何 Python 控制流 | 产物过 `StoryGraph.validate()` + 文件清单完整性检查才标记 `frozen` |

> 为什么这条隔离要「机制级」而非「文档级」:story_studio 与 Runner 共享同一 Python 包(`agent_world.hbm_demo`),一行 `get_world_db_path()` 就能误碰玩家存档;若 `config/stories/<id>` 与 `sim/<id>` 命名空间混用,「重新生成」可能覆盖正在运行的 world.db。靠「开发者自觉不 import」维持的红线终会被破。

### 1.3 工具内部结构(编排器 ≠ agent)

借鉴 AI4VN 的核心分离:`WorkflowController` 只做编排/落盘/回路控制,agent 只管单一 LLM 能力。

```
tools/story_studio/
  orchestrator.py        # 编排器(对标 AI4VN WorkflowController):管 Plan→Review→Revise 回路 + 落盘 + 幂等 + trace。不含 LLM 业务
  agents/
    designer.py          # 单一能力:brief → DAG 骨架(nodes/edges)
    casting.py           # 单一能力:brief + DAG → 角色/阵营/关系/能力
    writer.py            # 单一能力:补全 signals/endings/judges/timed_events/agent_behaviors
    producer.py          # 单一能力:审核(critique),非生成者
    artist.py            # 单一能力:出静态 assets(背景/头像/封面)
  base_agent.py          # call_json_with_schema(生成→schema 校验→失败回灌重试一次→仍失败 raise),对标 AI4VN base_agent.py:27
  authoring_schemas.py   # 生成期中间产物 schema(区别于运行期 Story Pack schema)
  brief_schema.py        # story brief 输入契约
  cli.py                 # generate / regenerate / validate / review / assets 子命令
  prompts/               # 各 agent 的 prompt 模板(质量几乎全押在这,对标 AI4VN config.py)
  logs/                  # 生成 trace + 失败产物归档(对标 AI4VN logs/image_log/FAILED_*)
  tests/                 # 录制-回放 fixture + 确定性断言
```

**规约**:回路控制(最大轮数、超限放行、feedback 回灌)和落盘只在 `orchestrator.py`,**不得**塞进任何 agent。

---

## 2. 用户输入规范:semi-structured story brief

### 2.1 为什么必须结构化(而非 AI4VN 的「一坨散文」)

AI4VN 的输入是 `requirements`(自由散文,可为空→AI 自由发挥)+ 可选结构化 OC。但 HBM 这类故事有**强约束**:玩家是外来访客、7 个角色带固定阵营 `{leader,tech_vp}` vs `{suppliers}`、4 幕、3+1 结局。这些**驱动 DAG 规模与拓扑的关键参数**,若不结构化表达,LLM 从一句话稳定抽取必然漂移(dev_logs/43 自己承认「节点拓扑/触发条件/权限分配难从一句话稳定抽取」)。

因此 brief = **自由文本 premise(交 AI 发挥的部分) + 结构化约束字段(必须遵守、可锁定的部分)**。

### 2.2 字段定义(`brief.yaml`)

| 字段 | 类型 | 必填 | 语义 | 空/缺省行为 |
|---|---|---|---|---|
| `premise` | string(自由文本) | 否 | 世界设定/基调散文,塞进 Designer prompt 的 `{premise}` | 空→AI 完全自由发挥(对标 AI4VN 空 requirements) |
| `tone` | string | 否 | 基调(如「商战、紧张、略带黑色幽默」) | 空→AI 据 premise 推断 |
| `player.identity` | string | **是** | 玩家身份(如「外来供应商代表」) | — |
| `player.role` | string | 是 | 玩家在 roles 表里的角色名(如 `player`) | — |
| `player.is_outsider` | bool | 否 | 是否外来访客(影响初始 place / 可达性) | 缺省 false |
| `target_acts` | int | 否 | 期望幕数提示,驱动节点规模(HBM=4) | 缺省由 AI 据 premise 定,validate 不强制等值 |
| `target_nodes` | int 或 range | 否 | 期望节点数提示(对标 AI4VN `TOTAL_NODES`) | 缺省 AI 自定 |
| `characters[]` | list | 否 | 关键角色意图,逐角色见下 | 空→AI 据 premise 造全部角色 |
| `characters[].name` | string | 否 | 角色名 | 空→AI 命名 |
| `characters[].faction` | string | 否 | 阵营标签(同标签归一阵营) | 空→AI 分派 |
| `characters[].is_protagonist` | bool | 否 | 是否主角 | 缺省 false |
| `characters[].personality` | string | 否 | 人设(只写人格/价值观,**不写「第几幕做什么」**) | 空→AI 补 |
| `characters[].appearance` | string | 否 | 外貌(供 Artist 出头像) | 空→AI 补 |
| `characters[].locked` | bool | 否 | **锁定位**:true 则已填字段冻结,AI 不得改写(对标 AI4VN 锁定规则) | 缺省 false |
| `endings_spec[]` | list | 否 | 想要的结局走向 | 空→AI 据 premise 设计 3-4 个结局 |
| `endings_spec[].id` | string | 否 | 结局 id(如 `join` / `cold` / `bad_reject`) | 空→AI 命名 |
| `endings_spec[].condition_hint` | string | 否 | 触发条件自然语言提示(如「trust≥25 且玩家选择加盟」) | 空→AI 设计 |
| `constraints[]` | list[string] | 否 | 硬约束清单(如「玩家不能物理走动找人,只能发消息/见面」「禁用现代术语」) | 空→无额外约束 |
| `art_style_hint` | string | 否 | 画风提示,供 Artist | 空→AI 定 |
| `language_style_hint` | string | 否 | 语言风格提示(大白话/禁用术语),供 Writer 产 `language_style.yaml` | 空→AI 定 |

**锁定规则(对标 AI4VN `designer_agent.py:54-62`)**:`locked: true` 的角色,其**已填字段**被冻结,Casting agent 只能补**空字段**;`locked: false` 或缺省时 AI 可自由改写/扩充。

### 2.3 填写示例(HBM 故事的 brief)

```yaml
# config/stories/hbm_memory_war/brief.yaml
premise: >
  一家芯片巨头要在显存(HBM)涨价潮里稳住自己的供应链。玩家是一个外来的
  小供应商代表,想挤进巨头的核心朋友圈拿到长期订单。巨头内部有强势的
  创始人、务实的技术 VP、和几家彼此竞争的现有供应商;还有一个想搅局的
  对手。整体基调:商战、信息差博弈、谁先建立信任谁赢。
tone: 商战、紧张、信息差博弈、略带黑色幽默

player:
  identity: 外来小供应商代表
  role: player
  is_outsider: true

target_acts: 4
target_nodes: 12

characters:
  - name: Jensen
    faction: incumbent_core
    personality: 强势、果断、护短、重视忠诚;只认能交付的人
    appearance: 黑色皮夹克,银发,中年男性
    locked: true                 # 我已写好,AI 别改
  - name: 技术 VP
    faction: incumbent_core
    personality: 务实、抠技术细节、对玩家的方案半信半疑
    locked: false
  - faction: suppliers            # 名字交给 AI
    personality: 现有供应商,彼此竞争,排斥外来者
  - name: 对手代表
    faction: disruptor
    personality: 想搅局,会散布对玩家不利的信息
    locked: false

endings_spec:
  - id: join
    condition_hint: 信任值 trust >= 25 且玩家在 Turn25 选择加盟
  - id: seed
    condition_hint: trust 中等,拿到一轮种子订单但未进核心圈
  - id: cold
    condition_hint: trust < 15,被礼貌性拒绝
  - id: bad_reject
    condition_hint: 玩家言行触发对方反感被当场逐出(坏结局)

constraints:
  - 玩家不能物理走动找人,只能发消息或被安排见面(社交层才是推进扳机)
  - 禁用穿越式现代网络梗

art_style_hint: 写实商务插画风,冷色调
language_style_hint: 大白话为主,允许少量行业黑话
```

---

## 3. 工作室流水线

### 3.1 总览数据流图

五个管理 agent 串成流水线,每步带一对「生成→Producer 审核」回路(详见 §4)。阶段间**靠落盘文件解耦**(对标 AI4VN 三阶段),每步可独立重入、断点续跑。

```
                         brief.yaml (用户输入,§2)
                              │
              ┌───────────────┼───────────────────────────────────────────┐
              ▼               │                                           │
        ┌──────────┐         │  ── Plan → Review → Revise 回路(§4)──     │
        │ Designer │◄────feedback───┐                                     │
        └────┬─────┘                │                                     │
             │ DesignerOutput        │                                     │
             │ (nodes骨架+edges骨架)  │                                     │
             ▼                       │                                     │
        ┌──────────┐                 │                                     │
        │ Producer │── critique ─────┘  审 DAG(无环/可达)+ 跑 validate()  │
        └────┬─────┘     + 分配各节点 active/passive/frozen/inject 权限     │
             │ ProducerReport(权限注入后的图 + 校验报告)                     │
             ▼                                                             │
        ┌──────────┐                                                       │
        │ Casting  │  brief.characters + DAG → agents/relations/...        │
        └────┬─────┘                                                       │
             │ agents.yaml / relations.yaml / relation_types.yaml          │
             │ groups.yaml / places.yaml / coverage / capabilities         │
             ▼                                                             │
        ┌──────────┐                                                       │
        │  Writer  │  整合补全:signals/endings/judges/timed_events         │
        └────┬─────┘  + 每节点 agent_behaviors + language_style/ui_text     │
             │  (完整 Story Pack 草案,17 YAML)                            │
             ▼                                                             │
        ┌──────────┐                                                       │
        │ validate │  确定性硬闸(§4):无环/可达/引用闭合/rdc_pair⊆allowed... │
        └────┬─────┘  失败 → 定点回灌对应 agent 重生(§4.3),非全推倒        │
             │ PASS                                                        │
             ▼                                                             │
        ┌──────────┐                                                       │
        │  Artist  │  读 agents/places/ui_text → 用 tapnow 出 assets/      │
        └────┬─────┘  背景(无人横版)→头像/立绘(纯底竖版)→封面;白底+抠图   │
             │  assets/*.png + ui_text.assets 映射                         │
             ▼                                                             │
   config/stories/<id>/ 整包(frozen)  ──► 交用户审阅/微调(§5)
```

### 3.2 逐 agent 契约

每个 agent 的输出都过 `call_json_with_schema`(对标 AI4VN `base_agent.py:27`):**生成 → schema 校验 → 失败回灌错误重试一次 → 仍失败 raise**。这是「降低多 agent 协作字段漂移」的底座,也是 §4 重生成回路的最底层。

#### (1) Designer — 出 DAG 骨架

| 项 | 内容 |
|---|---|
| **输入契约** | `brief.yaml`(全量) |
| **输出契约** | `DesignerOutput`(生成期中间产物,**非最终 Story Pack**):`{ nodes:[{id, beats_label, node_type:{normal\|merge\|ending}, knowledge_key, summary}], edges:[{from, to, trigger_hint(自然语言), choice_text?}] }`。**此时不含权限、不含精确 trigger 类型**。硬校验:节点数落在 `brief.target_nodes` ±容差,必有 `root`,必有 ≥1 个 `ending` 节点(对标 AI4VN `designer_agent.py:115` 硬校验节点数,不符直接 raise) |
| **产出哪个文件** | `story_graph.yaml` 的 `nodes[]` / `edges[]` **骨架部分**(后续被 Producer 注权限、Writer 注 trigger 精化) |
| **借鉴 AI4VN** | `designer_agent.py:35/86`(先 outline 再 story_graph,显式禁止 outline 含 story_graph);我们合并为一步直接产 DAG 骨架 |

#### (2) Producer — 审核 + 分配权限(审核者 ≠ 生成者)

| 项 | 内容 |
|---|---|
| **输入契约** | `DesignerOutput` |
| **输出契约** | `ProducerReport`:`{ is_valid:bool, errors:[{kind, node_id?/edge_id?, msg}], node_permissions:{node_id:{active_agents, passive_agents, frozen_agents, inject_agents, allowed_rdc_pairs, player_place, player_f2f_recipient}} }`。Producer 用 **ReAct + 真实工具**(对标 AI4VN `producer_agent.py:64`):可调 `graph_validate` / `enumerate_paths` 工具做客观结构校验(`tool_registry`),再 finalize 给 PASS/REVISE。**硬校验失败一票否决**(对标 `producer_agent.py:94-99`:`is_valid==False` 立即返回反馈) |
| **产出哪个文件** | 把权限注入回 `story_graph.yaml` 各 `node`;校验报告落 `logs/producer_report.json` |
| **借鉴 AI4VN** | 「生成者≠审核者」+「确定性硬闸 + LLM 软评审」双层(`producer_agent.py:64-120`):结构合法性走确定性工具一票否决,分支差异性/节奏走 LLM + `enumerate_paths` 数据软评审 |

#### (3) Casting — 出角色/阵营/关系/能力/地点

> AI4VN 把这块塞进 Designer outline;我们**单列一个 Casting agent**,因为 HBM 的世界原语(relations/relation_types/capabilities/coverage)是 dev_logs/42 §9 补的重点,需专门处理锁定规则与关系互斥语义。

| 项 | 内容 |
|---|---|
| **输入契约** | `brief.characters[]`(含 `locked`) + `DesignerOutput`(知道有哪些节点/地点提示) |
| **输出契约** | 多文件 dict,每个过对应 Story Pack schema 片段。锁定规则:`locked:true` 角色已填字段冻结,只补空字段 |
| **产出哪些文件** | `agents.yaml`(角色表 + `roles{role→id}` + `factions{name→[id]}` + `capabilities[]/soul_template/long_term_goal/initial_state`)、`relations.yaml`(初始关系边,`src_role/dst_role` 解引用 roles)、`relation_types.yaml`(逐类型 `is_contact/symmetric/mutually_exclusive/project_to_pool/display_template`——**这是 RDC 远端可达 + 互斥校验的唯一配置源**,dev_logs/42 §9.3 缺口②)、`groups.yaml`、`places.yaml`(含 `coverage[]`)、`place_behaviors.yaml` |
| **借鉴 AI4VN** | OC 锁定规则(`designer_agent.py:54-62`);`neutral_image_path` 参考图思路留给 Artist |

#### (4) Writer — 整合补全控制流 + 行为卡

| 项 | 内容 |
|---|---|
| **输入契约** | 注权限后的 `story_graph.yaml` + Casting 产出的角色/地点文件 + `brief`(tone/endings_spec/constraints/language_style_hint) |
| **输出契约** | 完整 Story Pack 草案的剩余文件,逐文件过 schema |
| **产出哪些文件** | `signals.yaml`(`valid_signals` + `keyword_sets` + `intent_heuristics`,消灭硬编码 tuple)、`endings.yaml`(`endings[]` 决策表 + `fallback_ending` + `bad_end`)、`judges.yaml`(scoring 维度/tech_keywords/system_prompt + LLM 裁判 prompt + ending_descriptions)、`timed_events.yaml`(events + group_action + capability_grant/revoke)、每节点的 `agent_behaviors{}`(见下「行为卡」)、`language_style.yaml`、`ui_text.yaml`、精化 `story_graph.yaml` 各 edge 的 `trigger`(把 Designer 的 `trigger_hint` 落实成 `story_signal/rdc_chain/...` 精确类型 + `state_updates` 写 `<to>_start_tick`,见 §4.2 时间窗口不变量) |
| **借鉴 AI4VN** | Writer 切片+导演+润色(`writer_agent.py`);我们的 Writer 不演台词(那是运行期演员),只补**控制流数据 + 行为卡** |

**行为卡 schema(落实 dev_logs/42 §9.3 缺口③,把 240+ 行 `if aid==N and phase=='X'` 表驱动化)**:

每节点 `agent_behaviors[aid].rules` 是**按声明顺序匹配的条件分支列表**:

```yaml
agent_behaviors:
  3:                              # tech_vp 在某节点
    rules:
      - when: { has_unread_rdc: true }            # 谓词全真者生效,按声明顺序取首个
        respond_rule: 先回应未读的 RDC 私信,再决定是否发言
        length_rule: 2-3 句
        tool_constraints: [send_message, relation_change]
        keywords_to_watch: [良率, 交付周期]
      - when: { has_player_inject: true }
        respond_rule: 针对玩家刚抛出的方案追问技术细节
        length_rule: 1-2 句
      - when: {}                                  # 兜底(空 when 恒真)
        respond_rule: 保持观望,不主动发言
        length_rule: 1 句
```

谓词求值上下文 `BehaviorCtx{ has_unread_rdc(aid), has_player_inject(aid), turn, node_id }` 由 `hbm_agent` 在装配 prompt 时构造。**立规约**:`soul` 只写人格/情绪/价值观;所有「第几幕做什么/调什么工具/发给谁」一律落 `node.agent_behaviors`,不得写进 soul 字符串。

#### (5) Artist — 出设计期静态资源(tapnow)

> **关键区分**:本步是**设计期静态资源**(离线 authoring),与本分支 `f18_scene_render`(运行期实时帧渲染,进 Runner)**生命周期不同**,二者可共享 prompt/consistency 代码但**绝不混淆**。f18 每帧重画;Artist 出**稳定的**背景/头像,落盘一次复用。

| 项 | 内容 |
|---|---|
| **输入契约** | `agents.yaml`(角色 + appearance)、`places.yaml`(地点)、`ui_text.yaml`、`brief.art_style_hint` |
| **输出契约** | `assets/*.png` + 写回 `ui_text.yaml` 的 `assets` 映射(角色 id→头像路径、地点 id→背景路径) |
| **产出顺序(照搬 AI4VN `run_render_phase`)** | ① 场景背景(无人、横版 1792x1024,prompt 强制 `no_human`)→ ② 角色头像/立绘(纯白底、竖版、半身、正面;表情维度可由剧本扫描动态扩充)→ ③ 标题封面(用各角色 neutral 当参考保一致性) |
| **一致性策略** | 先出**主角 neutral 当全局风格基准**,其他角色以主角图为参考但文字约束「别复制主角的脸」;同角色多表情锁自己的 neutral 当锚。一致性靠「参考图 + 文字约束」而非纯 prompt |
| **后处理** | 白底生成 + `rembg`(isnet-anime)抠透明立绘(比直接让模型出透明底稳) |
| **幂等** | 以「角色 id / 地点 id / 表情名」为稳定文件名,**存在即跳过**——反复点「重新生成」只补缺失的,省钱省时(对标 `artist_agent.py:143`) |
| **审图回路(可选)** | tapnow 不带审核时,另起一个审核 agent 读图给 PASS/REVISE,feedback 回灌重生 + 把上一张失败图当反面参考图传回(对标 `workflow.py:508/597`),最多 3 次,超限保留最后一张,失败样本归档 `logs/image_log/FAILED_*` |

---

## 4. validate 闸门

### 4.1 两层闸门(对标 AI4VN「确定性硬闸 + LLM 软闸」)

| 层 | 谁执行 | 性质 | 失败后果 |
|---|---|---|---|
| **硬闸(本节主体)** | `StoryGraph.validate()` + Story Pack 引用闭合校验,**确定性** | 一票否决,结构合法性 | 触发 §4.3 定点重生成回路 |
| **软闸** | Producer LLM + `enumerate_paths` 数据 | 软评审,分支差异性/节奏质量 | 返回结构化 feedback 驱动重生 |

> **两个 validate 不要混淆**:本节是**生成期校验闸门**(authoring 内部,失败→回灌重生);运行期 `load_story_pack` 还有一道**加载期门禁**(失败→`routes.py` 返回 400,阻止 seed)。二者**复用同一套不变量**,但触发时机与失败处理不同。

### 4.2 硬校验不变量逐条

借鉴 AI4VN `story_graph.py:99-122` 的最小集(V1-V3),并**补强 AI4VN 已知缺口**(它 validate 只查 3 类,可达/孤儿/路径质量全缺)。下表 ✅=AI4VN 已有可照搬,⭐=AI4VN 缺口我们必须补:

| # | 不变量 | 来源 | 校验逻辑 |
|---|---|---|---|
| **V1** ✅ | **引用闭合(边引用的节点必须存在)** | AI4VN `story_graph.py:107-111` | 每条 edge 的 `from`/`to` ∈ `nodes` keys,否则报「边引用了不存在的节点」 |
| **V2** ✅ | **无环(DAG)** | AI4VN `story_graph.py:114-116` | Kahn 拓扑排序(BFS 入度法),`len(result)!=len(nodes)`→有环→报「图中存在环路」 |
| **V3** ✅ | **存在 root 起始节点** | AI4VN `story_graph.py:119-120` | `'root' in nodes`,否则报「缺少 root 起始节点」 |
| **V4** ⭐ | **所有声明的 ending 可达** | AI4VN `get_reachable_endings` 有算法**但未接入** validate | 从 root DFS,断言每个 `node_type==ending` 节点 ∈ 可达集 |
| **V5** ⭐ | **无孤儿/不可达节点** | AI4VN 拓扑排序不捕获 | root-可达集 == 全节点集;`root` 外不得有入度 0 节点(无第二 source) |
| **V6** ⭐ | **无死路(非 ending 节点必有出边)** | dev_logs/42 §7 | 每个 `node_type!=ending` 节点 `len(get_edges_from)>0` |
| **V7** ⭐ | **rdc_chain pair ⊆ from_node.allowed_rdc_pairs** | dev_logs/42 §7 | 每条 `trigger` 含 `rdc_chain` 的 edge,其 pair ⊆ `from` 节点的 `allowed_rdc_pairs` |
| **V8** | **角色/地点/agent/relation/capability 全量解引用** | dev_logs/42 §7 | `edges.actions.agent_moves`/`inject` 引用的 role、`place_mutations` 引用的 place label、`relations.src/dst_role`、`agent_behaviors` 的 aid 全部能在 `agents.roles`/`places`/`place_behaviors` 解引用 |
| **V9** | **relation 双方存在 + relation_type 已声明** | dev_logs/42 §9.3 缺口② | 每条 `relations[]` 的 `src_role`/`dst_role` ∈ `agents.roles`,且 `type` ∈ `relation_types`;`mutually_exclusive` 引用的类型也须存在 |
| **V10** | **signal 谓词合法** | dev_logs/42 §3 | `endings.when`/`edges.trigger.condition` 的 safe_eval 表达式只用白名单变量 `{trust, intent, beats_label, turn, flags}`,AST 只含比较/布尔,无函数调用/属性/下标(对标 dev_logs/42 §4.3) |
| **V11** ⭐ | **node id 字段 == dict key** | AI4VN 不校验(潜在缺口) | 每个 `nodes[key].id == key` |
| **V12** ⭐ | **merge 节点入度匹配** | AI4VN `is_merge_point` 有算法**未接入** | `node_type==merge` 的节点实际入度 >1;`normal` 节点不得多父(或显式允许,二选一定死) |
| **V13** ⭐ | **choice 文本非空/去重** | AI4VN 不校验 | 同一节点的多个 `choice_text` 出边不得为空、不得重复 |
| **V14** | **时间窗口 start_tick 完整性** | 缺口(隐式不变量) | **每个有出边且出边含 `rdc_*`/`f2f_keyword`/`story_signal` trigger 的非 root 节点,其所有入边的 `actions.state_updates` 必须写 `<node>_start_tick`(或统一 `node_start_ticks[node]`)**。否则运行期 detect 会退回 `root.start_tick`,用错时间窗口下界(detect 用 `(since_t, t_now]` 半开区间),导致跨幕旧消息污染/重复触发/提前推进,而当前无此校验→错配只在运行时表现为诡异路由 |
| **V15** | **agent_behaviors when 谓词合法** | 缺口③ | `rules[].when` 的键 ∈ 已定义谓词集 `{has_unread_rdc, has_player_inject, turn_gte, ...}`;每条 rules 链必须有一条兜底(空 when 或恒真) |
| **V16** | **schema_version 受支持** | 缺口17 | `meta.schema_version` ∈ `SUPPORTED_SCHEMA_VERSIONS`,缺失或越界 raise |

> safe_eval 覆盖 4 结局条件(含 `trust==25`/`trust==15` 边界)的单测必须全绿;**禁用 Python `eval()`**,用 `simpleeval` 或自研受限编译器。

### 4.3 校验失败 → 定点重生成回路(只重生成出问题的 agent 产物,非全推倒)

这是本工具区别于「一次性冻结」的核心机制(dev_logs 把它压缩成「循环到 validate 通过」一句话,缺机制三要素)。借鉴 AI4VN `_review_and_revise`(`workflow.py:145`)的「有界回路 + 超限放行 + 全程留痕」。

**回路三要素**:

1. **生成者 ≠ 审核者**(已由 §3 分工保证:Producer 审 Designer/Writer 产物)。
2. **最大轮数 + 超限处理**:每对生成-审核最多 `N` 轮(默认 3,可配)。超限时**二选一定死**:`needs_human`(强制放行 + 打标交人工)而非 AI4VN 的无脑放行——因为我们的不变量(可达/rdc 子集)破了直接放行会让运行期崩,故 HBM 选 **raise 给人工**,不静默放行不可达图。
3. **feedback 结构化回灌 + 定点重生**:

**定点路由表**(validate 报的 error.kind → 回灌给哪个 agent → 只重生哪个产物):

| error.kind(违反的不变量) | 回灌目标 agent | 只重生的产物 | 不动的产物 |
|---|---|---|---|
| V2 有环 / V4 不可达 / V5 孤儿 / V6 死路 / V11 id 不符 / V12 merge 入度 / V13 choice | **Designer** | `story_graph` 的 nodes/edges 骨架 | agents/relations/signals/endings... 全保留 |
| V7 rdc_pair 越界 | **Producer** | 对应节点的 `allowed_rdc_pairs` 权限 | 图结构、其他文件保留 |
| V8/V9 解引用失败 / relation 双方不存在 | **Casting** | `agents`/`relations`/`relation_types` | 图结构保留 |
| V10 signal 谓词非法 / V14 start_tick 缺 / V15 when 非法 | **Writer** | `signals`/`endings`/对应 edge 的 trigger/`agent_behaviors` | 图骨架、角色保留 |
| V16 schema_version | (工具自身) | 写正确版本号 | — |

**回灌格式**(对标 AI4VN「把错误信息回灌 prompt 重试」+ `base_agent.py:46-66`):把 `errors[]` 里**具体的 node_id/edge_id + 中文不变量描述**合并进对应 agent 的 prompt 末尾(如 AI4VN 的「IMPORTANT CORRECTIONS」追加法),让 agent 知道**改哪个节点的什么**,而非重产全图。

**失败留痕**:每轮不通过,把失败产物 + 元数据(违反不变量/feedback/轮次)落 `logs/FAILED_<agent>_<round>.json`(对标 AI4VN `logs/image_log/FAILED_*`),供事后分析与 trace。

**幂等保证局部重生**:orchestrator 以 `node_id`/`agent_role`/文件名为稳定 key,「产物已存在且无修改请求则跳过」(对标 AI4VN `artist_agent.py:143` / `workflow.py:677`)。重生只覆盖被路由到的切片,其余原样保留。

---

## 5. 人在环:审阅 / 微调

流水线第四环。先做 **CLI + JSON/文本 diff**,UI 后置(这块 AI4VN 没有参照,是 hbm_demo 从零设计)。

### 5.1 审阅入口:`story_studio review <id>`

生成后 dump **人类可读摘要**(而非让用户读 17 个裸 YAML):

- **节点图 ASCII**:DAG 的拓扑可视化(节点 + 边 + choice_text)。
- **各节点权限表**:每节点 `active/passive/frozen/inject` agent + `allowed_rdc_pairs` + `player_place`。
- **四结局路径列表**:`enumerate_all_paths(start="root")` 枚举所有 root→ending 路径,逐条列出经过的节点 + 命中的结局 id,供人工核对「join/seed/cold/bad 四条路径是否都在、是否合预期」。
- **角色/关系摘要**:roles/factions 表 + relations 边 + 每角色 soul 摘要。

### 5.2 微调路径(两条,定死边界)

| 路径 | 操作 | 重跑 validate |
|---|---|---|
| **A. 改 brief 重生** | 编辑 `brief.yaml` → `story_studio regenerate`(可带 `--node`/`--agent`/`--file` 局部,见 §5.3) | 自动跑 §4 完整回路 |
| **B. 直接改冻结后的 YAML** | 用户手改 `config/stories/<id>/*.yaml` → **必须** `story_studio validate <id>` | **强制重跑 validate() 才能重新标记 `frozen`**;违反任一不变量则报告具体违反项(无环/可达/rdc_chain 子集/解引用),拒绝 frozen |

> 红线:直接改 YAML 后**不重跑 validate 不得标记 frozen**——防止人工微调静默破坏不变量(如改 edge 引入环、删节点造成不可达)。

### 5.3 部分重生成命令(局部重生,非全盘推倒)

借 AI4VN 幂等模式(稳定 key + 存在即跳过),支持迭代式局部修改——这是「微调」的本质(用户只想改第 3 幕一个触发条件,不该把整包推倒)。

```
story_studio regenerate <id> --node <node_id>      # 只重生该节点的骨架/权限/行为卡,重跑全图 validate
story_studio regenerate <id> --agent <role>        # 只重生该角色的 soul/relations 片段
story_studio regenerate <id> --file <name.yaml>    # 只重生指定文件
story_studio assets <id> --char <id> [--expr <e>]  # 只补该角色/表情的图,其余 assets 不动
```

**级联规约(明确哪些改动强制级联)**:

- 改 `edges` → **必须重跑全图 validate**(V2/V4/V5/V6/V7 都可能受影响),但**不必**重生 `agents.yaml`。
- 改某角色 soul → 只重生该角色片段 + 重跑解引用校验(V8/V9),不动图。
- 改 assets → 纯补图,不触发结构 validate。

---

## 6. 分阶段实现 G0–G6

**铁律(顺序对齐 dev_logs/42 P0 主线)**:**必须先有干净的 Story Pack 格式 + 解释器,再做生成工具。** 理由:本工具的唯一产出是 Story Pack,若下游 schema 和解释器没定死,生成工具产出的「正确性」无从校验(§4 全部不变量都依赖解释器侧 `StoryGraph.validate()` 与 `enumerate_all_paths`)。dev_logs/43 §6.2 同样明确「先解释器后管理者」「初版可全部手写 YAML,不必先上 LLM」。

| 阶段 | 与 dev_logs/42 主线对齐 | 目标 | 产出 | 验收 |
|---|---|---|---|---|
| **G0 前置(不属本工具)** | dev_logs/42 P0:Story Pack schema + `shared/story_graph.py` + `interpreter.py` 落地 | 干净 Story Pack 格式 + 解释器 + 加载期 validate() 就位;HBM 自身拆成 `config/stories/hbm_memory_war/` 手写 YAML 整包 | 17 YAML schema 冻结、`StoryGraph.validate()` 实现 §4.2 全部不变量、`enumerate_all_paths` 回归四路径 | 手写 HBM 包过 validate;解释器跑通 join/seed/cold/bad 四路径(逐帧等价回归 vs 旧 if 链) |
| **G1 契约 + 骨架** | 本工具起点(P0 之后) | 定 `brief_schema` + `authoring_schemas`(DesignerOutput/ProducerReport)+ `base_agent.call_json_with_schema` + orchestrator 骨架(纯落盘/回路,无 LLM) | `tools/story_studio/` 目录骨架 + 所有 schema + CLI 框架 | schema 单测全绿;orchestrator 能把**手写的** DesignerOutput 落成 story_graph.yaml 骨架;红线测试(import 图不含 seed/WorldDB/kernel)通过 |
| **G2 Designer + Producer + validate 回路** | — | Designer 产 DAG 骨架,Producer 审 + 注权限,validate 硬闸 + §4.3 定点重生回路打通 | `designer.py`/`producer.py`/validate 闸门/回路 | 喂 HBM brief → 产出过 V1-V7/V11-V13 的 story_graph 骨架;**故意注入坏图(造环/不可达)→回路定点回灌 Designer 修复**;超限走 needs_human |
| **G3 Casting + Writer 全量包** | — | 补齐世界原语(角色/关系/能力)+ 控制流(signals/endings/judges/timed_events)+ 行为卡;产**完整** Story Pack 草案 | `casting.py`/`writer.py` + 全 17 YAML 生成 | 喂 HBM brief → 产出整包过 §4.2 **全部** V1-V16;`enumerate_all_paths` 命中预期四结局集;节点数符合 `brief.target_nodes` |
| **G4 人在环 + 局部重生** | — | `review`/`validate`/`regenerate --node/--agent/--file` 子命令;微调两路径 + 级联规约 | CLI 全子命令 + ASCII 图 dump + 局部重生幂等 | 改 brief 一个节点 → `regenerate --node` 只重生该切片其余不变;手改 YAML 造环 → `validate` 报具体不变量并拒绝 frozen |
| **G5 Artist 静态资源** | dev_logs/42 §6 补「设计期静态资源生成」阶段 | 离线出 assets(背景/头像/封面),幂等落盘,写回 ui_text.assets;明确与 f18 运行期帧的生命周期隔离 | `artist.py`(tapnow,可复用 f18 的 client/prompt_builder/consistency 抽象) | 喂 HBM 包 → 出全角色头像 + 全地点背景 + 封面;`assets --char` 局部补图;白底+抠图透明立绘;存在即跳过 |
| **G6 可测试 + 可观测 + 成本护栏** | dev_logs/42 §8 回退/灰度 | 确定性回归(fixture 回放)、生成 trace、成本预算硬上限、schema_version + migration | tests/fixture + trace + 预算护栏 + `upgrade` 子命令 | CI 用预录 fixture 不真调 LLM,断言产物过 validate + 路径命中预期;trace 可重建生成决策链;超预算即停 |

---

## 7. 确定性 / 可测试性 / 成本 / 可观测性

### 7.1 生成工具自身的确定性与可测试性

> 痛点:运行期那套确定性(safe_eval、四路径回归、`director_enabled=false`)很严密,但生成工具是 LLM 驱动天然非确定,若不专门设计会与运行期形成断层。

- **降随机**:LLM 调用低 temperature(0.1-0.3)+ 可注入 seed。
- **录制-回放 fixture**:录 `brief → Story Pack` 的 fixture,CI 用 **eval 模式读预录,不真调 LLM**(对标 dev_logs/43 裁判回归数据集思路)。
- **断言归约到确定性图/schema**:核心断言**不依赖 LLM 文本逐字一致**,而是断言「产物过 `validate()` + `enumerate_all_paths` 命中预期结局集 + 节点数符合 `brief.target_nodes`」——把「生成正确性」归约到确定性 schema/图断言上。
- **gate 钩子**:story_studio 改了 prompt 后,CI 跑 fixture 回放 + 上述图断言,保证仍能产出合法包。

### 7.2 成本 / 耗时预算(生成期才是 LLM 与出图成本大头)

生成期是 LLM 密集:Designer→Producer→Writer × Plan-Review-Revise 最多 3 轮 × 每轮 `call_json_with_schema`(生成+校验+可能重试一次),再叠加 Artist(背景 + 每角色每表情立绘 + 封面,立绘按表情×角色**线性放大**)。

**预算表(单次完整生成上界)**:

| 项 | 调用次数上界 | 说明 |
|---|---|---|
| Designer | 1 + 回路重生(≤3) | DAG 骨架 |
| Producer | 审核 ≤3 轮(ReAct 内 ≤4 step) | 每轮可能调 graph_validate/enumerate_paths |
| Casting | 1 + 回路重生(≤3) | 角色/关系 |
| Writer | 1 + 回路重生(≤3) | 控制流 + 行为卡 |
| Artist 出图 | 背景数 + Σ(角色×表情) + 1 封面 | 审图回路每张 ≤3 次 |

**硬护栏**(orchestrator 设上限,超限即停并报告):`max_llm_calls`、`max_images`、`total_timeout`。`POST /scenario` 触发的后台任务加**全局并发配额 + 每用户限流**(防多用户并发生成拖垮 LLM 配额)。CI 用 fixture 避免回归时真烧钱。

> 估算:一次 HBM 规模生成(12 节点 / 7 角色 / 各 1-3 表情)粗算 LLM 调用 ~15-40 次、出图 ~20-40 张,端到端数分钟级、成本受 `max_*` 上限封顶。具体数值在 G6 实测后回填。

### 7.3 可观测性:生成 trace

每次生成落一条结构化 trace(`logs/trace_<id>_<ts>.jsonl`),供「生成跑错事后归因」:

- **每 agent 调用**:`{agent, input_digest, output_digest, schema_ok, retried}`。
- **每轮 validate**:`{round, is_valid, errors:[{kind, node_id/edge_id}], routed_to_agent}`(记录 §4.3 定点路由决策)。
- **超限事件**:`{agent, rounds_exhausted, action: needs_human}`。
- **Artist 审图**:`{char, expr, attempt, pass/revise, feedback}` + 失败样本路径。

trace 让人能完整重建「这包是怎么生成出来的、哪轮哪个不变量挂了、回灌给谁修的」,与运行期 routing trace(每条边为何命中)形成设计期↔运行期的端到端可观测闭环。

---

## 附:与 AI4VN 借鉴对照速查

| 我们的做法 | AI4VN 出处 | 我们的差异 |
|---|---|---|
| `call_json_with_schema` 生成+校验+重试一次 | `base_agent.py:27/46-66` | 同 |
| 编排器 ≠ agent | `workflow.py`(WorkflowController) | 同 |
| 生成者 ≠ 审核者 + 有界回路 + 超限处理 | `workflow.py:145/174` | 超限选 needs_human/raise,不无脑放行不可达图 |
| 双层闸门(确定性硬 + LLM 软) | `producer_agent.py:64-120` | validate 不变量从 3 条(V1-V3)补到 16 条 |
| 阶段间文件解耦 + 幂等(存在即跳过) | `artist_agent.py:143` | 用于局部重生 |
| Artist 资产顺序 + 一致性链 + 白底抠图 | `run_render_phase`/`artist_agent.py:342` | 用 tapnow,且严格区分设计期静态资源 vs f18 运行期帧 |
| `enumerate_all_paths` 路径回归 | `story_graph.py:160` | 用于 review dump + 生成正确性断言 |

---

文档完成。本章已覆盖任务要求的全部 7 个部分:定位与边界(§1)、story brief 输入规范含填写示例(§2)、五 agent 流水线含每 agent 输入/输出契约 + 产出文件 + 数据流图(§3)、validate 闸门含 16 条不变量逐条 + 定点重生成回路(§4)、人在环审阅/微调 + 部分重生成命令(§5)、分阶段 G0-G6 与 dev_logs/42 P0 主线对齐(§6)、确定性/可测试性/成本/可观测性(§7)。所有设计点均落到具体文件路径、CLI 命令、schema 字段或不变量,并逐条标注 AI4VN 借鉴出处与我们的差异。

由于 MEMORY.md 记录「所有报告须用中文」,且本任务是「写文档」而非「写 .md 文件」,我已将完整文档作为最终消息直接返回(未写入 .md 文件,遵守不创建报告文件的约束)。如需我把它落盘为 dev_logs 下的正式文档,请告知目标路径。
