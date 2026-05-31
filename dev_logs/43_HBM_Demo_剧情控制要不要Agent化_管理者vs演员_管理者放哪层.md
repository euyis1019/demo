# HBM Demo 剧情控制要不要 Agent 化：管理者 Agent vs 演员 Agent，以及管理者放哪一层

> 关联：dev_logs/40（剧情耦合清单）、dev_logs/41（参考 AI4VisualNovel 的 DAG/解释器）、dev_logs/42（剧情数据驱动化完整规划：故事 = DAG 节点图 + 确定性解释器，Phase 降为只读标签）。
> 本文回答用户新提的两个问题，并给出可落地的分层归属、模块布局与最小验证路径。

---

## 0. TL;DR（一句话结论）

1. **剧情控制应该「半 agent 化」，不是「全 agent 化」。** 把它拆成两类 agent 是成立的：**演员 agent**（玩家可见，实时 LLM 表演）和**管理者 agent**（理解剧情、拆节点、定权限人设、做活判断）。但管理者必须再切成两批：**生成期管理者**（离线产出配置，是绝对主力）和**运行期管理者**（只在极少数「活判断」点出现，是兜底）。
2. **管理者 agent 不应该写在「引擎层 / Flask 层 / Runner 层」里的任意单一一层** —— 因为这个问题本身把两批管理者混为一谈了。正确答案是：
   - **生成期管理者** → **独立离线 authoring 工具**（既不在引擎，也不进 Runner 的 world_loop，也不塞进 Flask 的 HTTP 请求周期）；产物是纯数据（dev_logs/42 的 Story Pack YAML）。
   - **运行期管理者** → **L2 features**（新增 `f08_director`，作为可开关的导演/裁判特性），由 L1 Runner 经 `integration/abcs.py` 白名单受控调用，**绝不放 L3 Flask**（薄传输层），也**不直接写进 world_loop**（避免和引擎生命周期强耦合）。
3. **运行期的剧情控制主体仍是 dev_logs/42 的确定性解释器**（表驱动、零 if 链、可回归）；运行期管理者只在「成交判定 / 意图分类 / 四维评分」这种确实需要 LLM 活判断的点上介入，且**只产数据、不改控制流**。
4. **三方案里推荐方案 C（混合）**：离线生成管理者产 Story Pack + 运行期确定性解释器为主 + 极少量 L2 导演/裁判 agent 兜底，默认 `director_enabled=false`（100% 确定性），高级场景再 opt-in。

---

## 1. 正面回答用户的两问

### 1.1 (a) 剧情控制该不该 agent 化？两类 agent 的划分成立吗？怎么分？

**该 agent 化，但要分清「agent 化」指的是什么。**

「Agent 化」有两种截然不同的含义，必须先把它们分开：

- **含义一（认知/创作 agent 化）**：让一个有 LLM 的 agent 去**理解整个剧情、把故事拆成节点、决定每个节点哪些 actor 有什么权限/人设**。这是**值得做**的——因为现在这套东西全靠人手硬编码在 `routing.py / scoring.py / agent_signals.py / hbm_agent.py` 里（dev_logs/40 列的「七类硬编码」），换个剧本要改 6 个文件。让一个管理者 agent 把这件事做掉，产物落成配置，这是真正的解耦红利。
- **含义二（运行时决策 agent 化）**：让一个 LLM agent 在**每个 tick / 每次路由**时实时拍板「现在走哪个节点、谁能说话」。这是**绝大部分不该做**的——理由见第 3 节（延迟、成本、不可测、不可回归）。

所以「剧情控制该不该 agent 化」的答案是：**含义一该，含义二只在极少数活判断点该。**

**两类 agent 的划分成立，而且正是 AI4VisualNovel 验证过的范式：**

| | 演员 agent（Actor） | 管理者 agent（Manager/Director） |
|---|---|---|
| 面向谁 | **玩家可见**（7 个 NPC：NVIDIA 系、CEO 系等） | **玩家不可见**（幕后） |
| 干什么 | 沉浸式实时演出，按人设当场生成对白 | 理解剧情、拆节点、分权限、做活判断/裁判 |
| 用不用 LLM | 用，**每 turn 实时调** | 生成期用（离线一次）；运行期极少用（只在裁判点） |
| 现状落点 | 已有，跑在 L1 Runner（`hbm_agent.py::perform_action_by_llm()`） | **没有**，现在是 `routing.py` 的 if/elif 链 + 几处 LLM 分类硬编码扮演了「管理者」 |

**怎么分（关键的二次切分）：管理者 agent 必须再分成「生成期」和「运行期」两批**，这是本文最核心的判断（见第 3 节）。不分这一刀，就会掉进「每 turn 请一个导演 agent 重新决定权限」的坑，破坏一致性、可测性和成本。

### 1.2 (b) 管理者 agent 该写在引擎层 / Flask 层 / Runner 层？

**结论：这三个选项都不完全对，因为它们对应的是「运行期」的三个进程位置，而管理者的主力工作在「生成期」。给出明确落点：**

#### 生成期管理者 → 独立离线 authoring 工具（不进引擎 / 不进 Runner / 不进 Flask 请求周期）

落到我们的真实约束逐条说明为什么：

- **不放引擎层（`agent_world/world` + `agent_world/agents` + `kernel`）**：引擎必须保持**故事无关**。引擎只认「世界、地点、agent、tick」，不认「Phase / 节点 / 结局 / 信任阈值」。把生成故事 DAG 的逻辑塞进引擎会污染引擎的通用性，违反「引擎是通用基座」的定位。
- **不放 L1 Runner（`core/runner/world_loop.py`）**：Runner 是**常驻异步世界循环**（`_loop()`），它的语义是「一 tick 一 tick 往前推」。生成故事配置是**一次性离线**操作，时间轴上和 tick 推进完全正交。若塞进 world_loop，要么挡 tick（启动前跑一大段 LLM pipeline），要么绑死到 world_step 生命周期，破坏「配置 → 冻结 → 消费」的清晰分离。而且 D2 规定 L1 只能经 `core/runner/integration/*` 调 L2，Runner 本身不该承载「多 agent 协作编排」这种复杂决策。
- **不放 L3 Flask 的 HTTP 请求周期里**：Flask 是**薄传输层 + session 管理**。把「DesignerAgent → ProducerAgent → WriterAgent 协作循环」（可能 30s–5min）塞进一个 HTTP 请求，会超时、会和前端交互耦合、多玩家并发生成会竞态。Flask 不该承载多 agent 协作编排。
  - （注：`POST /scenario` 这种 endpoint 可以**触发**生成，但真正的生成 pipeline 应跑在后台任务里，产物是文件 / DB，而不是同步在请求里算完返回。）
- **正解：独立离线工具**，建议落在 `agent_world/hbm_demo/story_authoring/`（独立 Python 模块）或 `scripts/` 下的 CLI。输入「故事需求文本 + 角色数 + 期望幕数」，输出 dev_logs/42 的 Story Pack YAML 到 `config/stories/<story_id>/`。它**永远不碰 world_state**，只通过 YAML 文件这个数据契约和运行期交互。这正是 AI4VN 的「生成期 vs 运行期」彻底解耦。

#### 运行期管理者（活判断/裁判）→ L2 features（新增 `f08_director`），由 L1 经 abcs 白名单调用，不放 Flask

- **为什么必须在 Runner 进程内执行（而不是 Flask 或独立进程）**：Ground 事实已确认——**所有 LLM 调用都发生在 Runner 进程**（演员决策、评分、路由分类）。运行期管理者要做的「Phase4 成交判定 / Turn25 意图分类 / 四维评分」全是 LLM 调用，必须在 Runner 内同步 `await`，不能丢给 Flask（IPC 通常 10–100ms 起，且 Flask 是薄层）。
- **为什么是 L2 而不是直接写进 L1 world_step**：把导演逻辑直接写进 `world_step.py` 会让它和引擎生命周期强耦合、不可单独开关、不可单独测试。放 L2（`f08_director/`）则：① 和 `f04_stats`（评分）、`f05_story_routing`（路由）平级，可复用 `judges.yaml`、读 session 状态；② 可通过 `turn_control.yaml::director_enabled` 开关；③ 由 L1 经 `integration/abcs.py` 白名单受控调用（新增一个 `run_director_judge` 导出），符合 D2/D3。
- **为什么不放 Flask（L3）**：同上，LLM 在 Runner、Flask 是薄传输层。Flask 只负责把裁判结果经 `world_delta` IPC 下发前端，不参与判断。

**一句话**：生成期管理者是「纯生产者」（离线产 YAML），运行期管理者是「受限消费侧的活判断器」（L2 feature，只在裁判点跑），两者都不该写进引擎，更不该写进 Flask 的请求周期。

---

## 2. 两类 agent 的完整职责划分（输入 / 输出）

### 2.1 演员 agent（Actor，玩家可见，沉浸式）

已存在，跑在 L1 Runner（`core/runner/hbm_agent.py`，实例化于 `kernel.py::build_kernel()`）。**本方案基本不改它的本质**，只改它「权限从哪来」。

- **输入**：① 自己的人设（soul/goal，来自 L0 `hbm_scenario.yaml`）；② 当前 tick 的上下文 `turn_context`（phase/player_turn/stats/llm_params，经 `world_step.set_tick_context()` 注入到 `_batch_turn_context`）；③ 装配好的知识（`build_agent_knowledge`）；④ 当前节点赋予它的权限（active/passive/frozen、是否被 inject、可用的 story_advance 信号白名单、行为卡 rules）。
- **输出**：① 一句台词 / 一个动作（`perform_action_by_llm()`）；② 可选的 story_advance 工具调用（`STORY_ADVANCE_TOOL` 的 6 个信号），作为「我想推进剧情」的**信号**。
- **关键改造点**：演员的权限（谁该 active/frozen/inject、能发哪些信号、行为卡内容）**从「运行期 if 链」改为「读当前节点的配置」**。配置由生成期管理者产出，演员运行期只读不判。

### 2.2 管理者 agent（Manager / Director，幕后）

按 AI4VN 范式拆成若干子角色，并按「生成期 / 运行期」两批落位：

**生成期子角色（离线，独立工具，一次性）：**

| 子角色 | 职责 | 输入 | 输出 |
|---|---|---|---|
| **设计官 DesignerAgent** | 解析需求文本 → 产出 DAG 拓扑 | 故事需求文本、角色数、期望幕数 | `story_graph.yaml` 的 `nodes[]`（节点 + beats_label）+ `edges[]`（from/to/trigger） |
| **制片人 ProducerAgent** | 审核 DAG（无环、结局可达）+ 为各节点分配权限 | Designer 的 DAG、scenario 的 agents 列表 | 校验报告 + 各节点 `active_agents/frozen_agents/inject_agents` 配置 |
| **编剧 WriterAgent** | 整合并补全元数据 | DAG + 权限 + 故事设定 | 完整 Story Pack：`story_graph.yaml`+`signals.yaml`+`endings.yaml`+`judges.yaml`+`timed_events.yaml` |

> 三角色走「Plan → Review → Revise」循环到校验通过，产物一次性冻结。**初版可以全部手写 YAML，不必先上 LLM**——schema 和解释器逻辑不依赖管理者是不是 LLM。

**运行期子角色（在线，L2 `f08_director`，仅在裁判点）：**

| 子角色 | 职责 | 输入 | 输出 | 红线 |
|---|---|---|---|---|
| **裁判官 JudgeAgent** | Turn25 意图分类、Phase4 成交判定、四维评分（vision/execution/trust/burnout） | 当前 world_state、对话历史、session 变量 | `(intent, trust, ...)` 数据 | **只产数据，不改控制流**——结果交 `endings.yaml` 决策表用 `safe_eval` 选结局 |
| **节奏官 PacerAgent（可选/进阶）** | 在 edge 触发后微调推进节奏（提前/延后某节点） | 当前进度、玩家参与度 | 建议（advise，非强制否决） | 默认关闭；开则需固定 seed / 多数表决降方差 |

- **裁判官**本质上是把现在散落在 `routing.py::classify_turn25_intent()`、`watcher.py::classify_phase4_conclusion()`、`scoring.py::score_player_turn()` 里的三处 LLM 调用，收编成一个有清晰边界的 L2 feature。它**不能**改 agent 权限、不能改 edge 转移、不能禁言演员——它只往 `session` 里写评分维度。

---

## 3. 关键判断：管理者必须分「生成期」和「运行期」两批

### 3.1 为什么不能「每个决策都实时 agent 化」

如果把每个剧情决策（走哪个节点、谁能说话、用什么人设）都交给一个运行期 LLM agent 实时拍板，对我们这种**实时多 agent 谈判游戏**有四个致命问题：

1. **延迟（Latency）**：演员 agent 本身每 turn 已经是 7 个并发 LLM 调用。再在每个关键点插一次导演 LLM（500ms–1s），会串联堆在玩家感知路径上，单 turn 响应时间可能 +20–50%。而确定性解释器的 `tick()` 是纯函数，~1–10ms。
2. **成本（Cost）**：纯确定性路由整局新增 0 次 LLM；全 agent 化导演每整局多 20–30 次 LLM 调用 + 更大的 context（导演要喂 world_state 摘要 + 近 N 条对话 + pending trigger，2000–5000 token/call）。多玩家并发时线性放大。
3. **不可测（Testability）**：确定性解释器「一条路径 = 一个 Python test case」，给定 `(YAML, world_state)` 必然同一 `next_node_id`。导演 LLM 有 sampling 方差，同一进度不同 seed 走不同线，单元测试退化成「统计性测试」，CI 成本倍增。
4. **不可回归 / 不可回放（Determinism）**：剧情主控流一旦交给 LLM，就**无法回放、无法复现 bug、无法做路径回归**（join/seed/cold/bad 四条路径不能被稳定遍历验证）。对一个要反复调试、要给不同玩家稳定体验的游戏，这是不能接受的。

### 3.2 正确的两批划分

- **生成期管理者（主力）**：在 session 初始化前**离线跑一次**，把「理解剧情 → 拆节点 → 定权限人设」一次性做完，冻结成 Story Pack。这把所有「认知/创作」类的重活前移到离线，运行期零认知负担。一致性天然保证（整局权限来自同一份冻结 YAML）。
- **运行期管理者（兜底）**：只在**确实需要活判断**的少数点出现——这些点的共同特征是「需要读懂自由文本对话、给出语义判断」，规则写不死：① Turn25 玩家意图（玩家可能反水/含糊）；② Phase4 是否真成交（对话语义）；③ 四维评分（主观评价）。其余所有路由推进、节点转移、inject 控制、信号检测，都是确定性解释器的活，**不请 agent**。

**判据**：一个剧情决策点要不要上运行期 agent，问一句——「这个判断能不能写成一张表 / 一个表达式 / 一次信号检测？」能 → 解释器；不能（必须读懂自由文本语义） → 才考虑 L2 裁判 agent，且只产数据。

---

## 3.5 三方案评审与推荐

| 维度 | 方案 A·离线生成期管理者（AI4VN 式） | 方案 B·运行时实时导演（Tick Loop 内） | 方案 C·混合（确定性为主 + 导演兜底） |
|---|---|---|---|
| 管理者落点 | 独立离线工具 | L1 Runner / world_loop 内常驻 | 生成期=离线工具；运行期=L2 `f08_director` |
| 运行期主控流 | 确定性解释器 | 解释器 + 导演实时审查/否决 | 确定性解释器（导演只在裁判点产数据） |
| 确定性 | 最高（路由 100% 确定，仅演员对白非确定） | 丧失（导演 LLM 采样决定路由） | 高（路由确定；只有评分/结局选择含 LLM 方差，且不碰路由） |
| 延迟/成本 | 最低（运行期 0 新增 LLM） | 最高（每决策点 +LLM，串联堆延迟） | 低-中（仅 2–3 次裁判 LLM/session，可异步/并发） |
| 可测/可回归 | 最强 | 最弱（退化为统计测试） | 强（base 层快照可测；裁判可录制回放） |
| 灵活性（应对玩家越界） | 较弱（冻结后不可动态改流向） | 最强（实时二阶决策） | 中（导演可微调评分/结局描述，不改流向） |
| 框架侵入 | 中（需实装解释器 + authoring 工具） | 大（侵入 world_step 三处钩子 + 非确定性引入） | 中（解释器 + 一个可开关 L2 feature） |

**推荐：方案 C（混合），默认 `director_enabled=false`。**

理由：
- **方案 B 用「实时导演」去补「框架不够灵活」，代价是把游戏的主控流（路由）交给 LLM，丢掉确定性/可回归/低延迟——对实时谈判游戏得不偿失，且会积累「用导演补框架缺陷」的长期债务。** 仅在「确实需要运行时动态改写流向」的特殊玩法才考虑，且应限制为 advise（非强制否决）。
- **方案 A 纯离线最干净、确定性最高，但完全没有运行期活判断**。而我们现状里 Turn25 意图、Phase4 成交、四维评分**本来就在用 LLM**（`routing.py`/`watcher.py`/`scoring.py`），强行去掉会降低裁判质量。
- **方案 C = A 的骨架 + 收编现有三处 LLM 裁判为一个受控 L2 feature**。它既拿到 A 的确定性/可回归/低成本，又保留了「必须读懂语义」那几个点的 LLM 活判断，且把活判断**严格关进 `f08_director`、只产数据、不碰路由**。这与 dev_logs/42 完全兼容（42 的解释器就是 base 层），落地风险最小、可 AB（`director_enabled` 开关）。

**取舍说明**：C 比 A 多一个 L2 feature 和 `judges.yaml` 的运行期消费，复杂度略升；但换来「裁判质量不退化 + 仍可开关回退到 100% 确定」。default 关闭保证基线确定性，高级场景再 opt-in 接受方差换体验。

---

## 4. 精确分层归属表

> 真实约束回顾：引擎 = `agent_world/world` + `agent_world/agents` + `kernel`（故事无关基座）；HBM demo 在其上分 L0 config / L1 Runner / L2 features / L3 Flask；D1–D5 依赖规则；Runner 与 Flask 是两个独立进程（Runner 跑常驻 world_loop + 所有 LLM 调用，Flask 是薄传输层）；L1↔L2 经 `core/runner/integration/abcs.py` 白名单桥接。

| 层 / 位置 | 放什么 | 不放什么 & 为什么 |
|---|---|---|
| **引擎层**（`agent_world/world`、`agent_world/agents`、`kernel`） | 通用世界基座：地点、agent 容器、tick 推进、LLM 客户端。**保持故事无关**。 | 不放任何 Phase/节点/结局/信任阈值/路由逻辑。引擎一旦认识「HBM 的故事」就丧失通用性。 |
| **L0 config**（`hbm_scenario.yaml`、`turn_control.yaml`，未来 `config/stories/<id>/`） | 演员人设、地点、分组、LLM 数值参数；F07 开关；**新增 `director_enabled`**；**新增 Story Pack 目录**（生成期产物落盘点）。 | 不放结构化路由代码——配置是数据，不是逻辑。 |
| **L1 Runner**（`core/runner/`） | ① 跑**演员 agent**（`hbm_agent.py`，已有）；② 运行期世界循环（`world_loop.py`/`world_step.py`）作为**配置消费者**：读 Story Pack、跑解释器、按节点配置 `pick_active`；③ 在裁判点经 `integration/abcs.py` 白名单**受控调用 L2 导演**（新增 `run_director_judge` 导出）。 | **不直接写导演/裁判逻辑进 world_step**（会和引擎生命周期强耦合、不可开关、不可单测）；**不放生成期管理者**（会挡 tick、绑死生命周期，违反「配置→冻结→消费」与 D2）。 |
| **L2 features**（`features/`） | ① `f05_story_routing` → **重构为解释器**（`interpreter.py`，表驱动消费 `story_graph.yaml`，零 if 链）；② `f04_stats` → 评分，复用 `judges.yaml`；③ **新增 `f08_director`** → 运行期裁判 agent（Turn25 意图 / Phase4 成交 / 四维评分），**只产数据不改控制流**，经 abcs 暴露入口。 | 不放生成期管理者（生成是一次性离线编辑环节，不是「运行期 feature」；放 L2 会被当 feature 每 tick 跑，语义全错）。 |
| **L3 Flask**（`http/`、`routes.py`、`game_service.py`） | 薄传输：HTTP session、player_turn 计数、task 轮询、把裁判结果经 `world_delta` IPC 下发前端；可提供 `POST /scenario` **触发**（不执行）生成期 pipeline。 | **不放导演/裁判 LLM 调用**（LLM 在 Runner，Flask 是薄层 + 跨进程，IPC 延迟不可接受）；**不在 HTTP 请求周期内同步跑生成 pipeline**（超时、竞态、耦合前端交互）。 |
| **独立离线 authoring 工具**（`story_authoring/` 或 `scripts/`） | **生成期管理者**：DesignerAgent/ProducerAgent/WriterAgent 协作，输入需求文本，输出 Story Pack YAML 到 `config/stories/<id>/`，离线校验（无环/可达）后缓存。 | 不依赖任何运行时代码、不碰 world_state；通过 YAML 文件这一数据契约与运行期解耦。 |

---

## 5. 与 dev_logs/42 的关系

### 5.1 对应关系

- **生成期管理者 = 自动产出 dev_logs/42 的 Story Pack。** dev_logs/42 §2.2/§3 定义的 16 个控制点的数据模型（`story_graph.yaml` 的 nodes/edges、`signals.yaml`、`endings.yaml`、`judges.yaml`、`timed_events.yaml`）**就是生成期管理者的产物规格**。无需新创 schema，管理者产出的 YAML 严格遵循 42 的 schema 即可。Designer 产 `nodes/edges`，Producer 产各节点 `active/frozen/inject` 权限并跑 42 的 `validate()`，Writer 补 signals/endings/judges。
- **运行期 = dev_logs/42 的确定性解释器为主 + `f08_director` 裁判 agent 兜底。** 42 的 `interpreter.py` 是 base 层（表驱动遍历 edges、匹配 trigger、dispatch actions，替代 `routing.py` 的 `node_a_applies/node_b_applies/node_c_applies` 三大 if 块）；裁判 agent 的输出 `(intent, trust)` 只参与 `endings.yaml` 的 `when` 安全表达式求值（替代 `resolve_ending_id()` 的 `if trust >= 25 ... elif >= 15`），**不产生解释器未定义的 edge/node**。
- **Phase 仍按 42 降级为 `beats_label`（只读显示标签）**，路由真值改由 `current_node_id` 驱动。

### 5.2 控制流图（从一句话剧情到运行）

```
【生成期 · 离线 · 独立 authoring 工具】（一次性，不进 Runner/Flask 请求周期）
  一句话/一段剧情需求文本
        │
        ▼  DesignerAgent（理解剧情 → 拆节点）
  story_graph.nodes[] + edges[](from/to/trigger)
        │
        ▼  ProducerAgent（审核无环/结局可达 + 分配各节点 active/frozen/inject 权限人设）
  权限配置 + validate() 通过
        │
        ▼  WriterAgent（整合 + 补 signals/endings/judges/timed_events）
  ┌──────────────────────────────────────────────┐
  │  Story Pack YAML  →  config/stories/<id>/      │  ← 冻结，数据契约
  └──────────────────────────────────────────────┘
        │
========│=========== 进程/时间轴边界（离线 → 在线）===========
        │
【运行期 · 在线 · L1 Runner 进程】
  session 启动 → world_loop 加载一次 Story Pack
        │
   每 tick：
     ┌─ [L2 解释器] interpreter.tick(world_state, current_node_id)
     │     ├─ 检测 edge.trigger（story_signal / rdc_chain / 表达式 / timeout）  ← 纯确定性，~ms
     │     ├─ 命中 → apply(edge.actions)（搬人/改地点/更新状态）
     │     └─ current_node_id := next
     │
     ├─ [L1 Runner] 按 node.active/frozen/inject 列表 pick_active
     │     └─ 并发调 7 个【演员 agent】perform_action_by_llm() → 实时对白  ← 唯一常规 LLM
     │
     └─ [仅在裁判点] L1 经 abcs 调 [L2 f08_director]（director_enabled 时）
           ├─ Turn25 意图分类 / Phase4 成交判定 / 四维评分  ← 少量 LLM
           └─ 产出 (intent, trust) → 交 endings.yaml 的 when 表达式 → 选结局节点
        │
   结果经 world_delta IPC → 【L3 Flask 薄传输】→ 前端
```

---

## 6. 模块布局建议与最小落地步骤

### 6.1 目录 / 文件布局

```
agent_world/hbm_demo/
├── config/
│   └── stories/
│       └── hbm_memory_war/                 # 现有故事的 Story Pack（生成期产物落盘）
│           ├── story_graph.yaml            # DAG: nodes + edges(trigger→actions)
│           ├── signals.yaml                # story_advance 白名单 + keyword_sets
│           ├── endings.yaml                # endings[].when 决策表 + bad_end
│           ├── judges.yaml                 # game_title + dimensions + LLM 模板
│           └── timed_events.yaml           # Turn N 定时事件
│
├── story_authoring/                        # 【新增·生成期管理者·独立离线工具】
│   ├── __init__.py
│   ├── designer_agent.py                   # 需求文本 → nodes/edges
│   ├── producer_agent.py                   # 审核 DAG + 分配节点权限
│   ├── writer_agent.py                     # 整合 → 完整 Story Pack
│   ├── story_graph.py                      # 可直接借鉴 AI4VN 的 StoryGraph（拓扑/可达校验）
│   └── cli.py                              # `python -m ...story_authoring.cli <需求文件>`
│
├── features/
│   ├── f05_story_routing/
│   │   ├── interpreter.py                  # 【新增】表驱动解释器（替代 routing.py if 链）
│   │   ├── routing.py                      # 逐步瘦身/退役为 interpreter 的薄封装
│   │   └── ...
│   ├── f04_stats/scoring.py                # 评分改读 judges.yaml
│   └── f08_director/                       # 【新增·运行期管理者·L2 可开关 feature】
│       ├── __init__.py
│       ├── judge_agent.py                  # Turn25 意图 / Phase4 成交 / 四维评分
│       └── config.py                       # is_director_enabled() 读 turn_control.yaml
│
└── core/runner/integration/
    └── abcs.py                             # 【改】新增 run_director_judge 等导出（L1↔L2 白名单）
```

### 6.2 最小落地步骤（每步可独立验证、可回退）

1. **Step 0 · 不动管理者，先验证解释器等价**（最关键）：实装 `interpreter.py`，把现有 HBM 故事手写成 `story_graph.yaml`，让解释器**逐帧复现**现有 `routing.py` 的 join/seed/cold/bad 四条路径。用 world_state 快照做回归断言「解释器输出 == 旧 if 链输出」。**这一步不引入任何 agent，纯验证数据驱动可行。**
2. **Step 1 · 收编裁判为 `f08_director`**：把 `classify_turn25_intent` / `classify_phase4_conclusion` / `score_player_turn` 三处 LLM 调用搬进 `f08_director/judge_agent.py`，经 abcs 暴露入口，加 `director_enabled` 开关（默认 true 以保持现有行为）。验证：开关开/关行为一致，结果只写 stats、不碰路由。
3. **Step 2 · endings 表驱动**：把 `resolve_ending_id` 的 `if trust>=25` 改成 `endings.yaml` 的 `when` 安全表达式求值，裁判输出 `(intent, trust)` 喂进去。验证四条结局路径仍正确。
4. **Step 3 · 造一个换皮 demo 故事**：手写第二份 `config/stories/<id2>/`（改地点/角色名，结构同构，Phase 仍 4 幕），验证「**只改 config 就能跑另一个故事**」。
5. **Step 4（可选/未来）· 上生成期管理者**：实装 `story_authoring/` 的三个 agent，让它从需求文本自动产出 Step 3 那种 YAML。此时后端 schema 和解释器**完全不动**——管理者只是把「手写 YAML」自动化。

> 顺序原则：**先解释器（确定性基座）后管理者（产配置）**。解释器是所有收益的地基；管理者是锦上添花，可以最后做、甚至长期手写 YAML。

---

## 7. 风险与兜底

| 风险 | 说明 | 兜底 |
|---|---|---|
| **把控制权交给 LLM 的不可控性** | 若让运行期 agent 决定路由（方案 B 路线），同一进度不同 seed 走不同线，bug 不可复现、路径不可回归。 | **红线：运行期 agent 只产数据、不改控制流。** 路由主控流永远在确定性解释器手里。`director_enabled=false` 时退回 100% 确定。 |
| **生成期管理者从自由文本抽不出可靠结构** | 「节点拓扑/触发条件/权限分配」难从一句话稳定抽取。 | 初版**手写 YAML / 向导 UI 辅助**，不依赖 LLM 可靠抽取；管理者 LLM 只做「草稿 + 人工校对」，且产物必过 `validate()`（无环/可达/引用完整性）才能加载。 |
| **裁判 LLM 评分不稳定** | 同对话两次评分可能不同，trust 在 24.9↔25.0 抖动直接翻结局。 | 低 temperature（0.1–0.3）；阈值边界加告警；可「多数表决 / 取均值」；录制裁判输入输出做回归数据集，CI 用 eval 模式（读预录、不真调 LLM）。 |
| **坏 Story Pack 导致运行期诡异错误** | DAG 配置错（死路、不可达结局、引用不存在的 agent）。 | 加载期强制 `StoryGraph.validate()` + `validate_judge_coverage()`（裁判输出至少匹配一个 ending），失败**阻止 session 启动**，给清晰错误报告。 |
| **冻结后无法运行时改流向** | 玩家越界行为（提前反水/要求提前结束）超出剧本。 | 这是有意取舍（换确定性）。需要弹性时用 `f08_director` 的节奏官做**有限 advise**（提前/延后节点，非凭空新增 edge），且只在 opt-in 时开启。 |
| **解释器重构期间回归风险** | 把 `routing.py` 三大 if 块换成表驱动可能引入行为差异。 | Step 0 的「逐帧等价回归」是硬门槛：解释器必须先在现有故事上和旧 if 链逐帧一致，才允许退役 `routing.py`。 |

---

## 附：与现有真实约束的对照速查

- **演员 agent 在 L1 Runner 跑** → 保持不变，只改「权限从配置读」（`hbm_agent.py` + `pick_active.py` 读 node 配置）。
- **所有 LLM 调用在 Runner** → 运行期裁判必须在 Runner（L2 `f08_director`，L1 经 abcs 调），不能丢 Flask。
- **Runner / Flask 两进程** → 裁判结果经 `world_delta` IPC 下发 Flask；生成期管理者完全离线，不参与任何 IPC。
- **L1↔L2 经 abcs 白名单** → `f08_director` 和 `interpreter` 的入口都要进 `abcs.py` 导出，world_loop 不绕过 abcs 直 import features（D2/D3）。
- **dev_logs/40 的「七类硬编码」/dev_logs/42 的「16 控制点」** → 全部成为生成期管理者的产物字段，运行期由解释器消费，零 if 链。
