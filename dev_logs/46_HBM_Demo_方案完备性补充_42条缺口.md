> 由多智能体工作流四维审计 + 完备性补漏综合而成(42 条缺口：17 blocker / 21 important / 4 nice-to-have)。对齐用户先前全部需求：只改config换世界 / phase→DAG / 涌现社交保留 / 硬骨架+自由演员 / 用户只写剧情agent生成 / 世界实时变化 / 关系&记忆实时。

# 方案完备性补充（并入 dev_logs）

> 说明：本章节由对全部完备性缺口清单去重归类整理而成。诚实起见，凡标 **blocker** 的项均已写明"不补则换故事会失败"的具体后果。已合并的重复项在该项下用「合并自」标注，不再单列。

---

## 阅读指南

- **严重度**：`blocker`（不补则换故事/迁移直接失败）＞ `important`（不补则有正确性/可维护性/可观测性硬伤，但不必然崩）＞ `nice-to-have`（增强，可后置）。
- 全章节按 **主题** 分四大类：A 换 config 完整性 / B 涌现 feature 与运行期控制 / C 运维生命周期与测试 / D 设计期生成流水线。每类内部 **blocker 在前，important 居中，nice-to-have 末尾单列**。
- 文末附「补充后方案对齐了哪些用户需求」的勾选对照表。

---

## A. 换 config 完整性（routing 表驱动覆盖 × Story Pack 落点逐条核对）

这一类的共同主线：dev_logs 声称"只改 config 就能换一个完全不同的故事"，但旧 `routing.py` / `agent_signals.py` / `watcher.py` 里的若干 `if` 分支，用现有 schema **表达不出来**。每补一条，就是把一个写死的控制分支真正搬进数据。

### A-1 [blocker] phase_timeout 触发器缺"负依赖"（unless）字段，bad_end 超时边无法表达

- **现状**：`agent_signals.py:240 detect_bad_end` 的超时分支是 `if player_turn >= limit and not detect_node_a(...)`——超时坏结局不仅看回合数，还硬性要求"另一条推进边此刻仍不成立"。但 dev_logs/42 §3 与 §4.2 的 `phase_timeout` schema 只有 `{type, from_node, max_turns}` 和 handler `turns_in_node(from)>=max`，完全没有 "AND NOT(另一条 advance 边的 trigger)" 这一项。
- **为什么是缺口**：照现 schema 翻译，玩家在第 10 turn 刚好完成审批 RDC 链时会被**误判为坏结局**（旧代码此处不判坏），破坏落地路线 §6.2 Step0 的"逐帧等价回归"硬门槛。
- **补到哪**：dev_logs/42 §3 trigger schema 章节 + §4.2 `TRIGGER_HANDLERS` 的 `phase_timeout` 定义。
- **具体补什么**：给 `phase_timeout` 增 `unless_edge: <edge_id>`（或 `unless_trigger: {...}`），语义＝回合达标且指定边 `detect()==False` 才命中；handler 改为 `turns_in_node>=max and not detect(resolve(unless_trigger), ctx)`。HBM 的 `root->bad_end` 边补 `unless_edge: "root->phase2"`。
- **不补的后果**：bad_end 超时边逻辑与旧版不等价，逐帧回归门槛直接挂，HBM 这一参考故事都无法无损复现。

### A-2 [blocker] detect 触发器的时间窗 `since_t` 无 schema——`state_updates` 只写不读

- **现状**：所有 RDC/F2F 检测依赖 per-node 时间窗（node_b 用 `phase2_start_tick`、node_c 用 `phase3_start_tick`、其余退回 `start_tick`），由上一条边副作用写入。dev_logs 把写入侧建模为 `state_updates`，但 §4.2 的 `rdc_chain/rdc_positive/rdc_expel` handler **没有任何字段告诉 handler 本次检测的 `since_t` 该读哪个节点的 start_tick**；`turns_in_node` 仅 `phase_timeout` 用到。
- **为什么是缺口**：换故事节点改名/增减时，`phase2/phase3_start_tick` 是写死命名；detect handler 不知道读哪个窗口，要么全用 `root.start_tick`（把上一幕旧 RDC 误算进来→提前推进/重复触发），要么需要 schema 显式声明窗口来源——而 schema 没有。
- **补到哪**：dev_logs/42 §4.2 interpreter（ctx 窗口约定）+ §2.2 Node schema（`node_start_ticks`）。
- **具体补什么**：RoutingCtx 定义 `ctx.window_since(node_id)` ＝该节点进入 tick，由通用 `session.node_start_ticks[node_id]` 维护（替代写死的 phase2/3_start_tick）；每个 `rdc_*` trigger 增 `window_from: <node_id>`（默认＝`edge.from`），handler 用 `ctx.window_since(spec.get('window_from', edge['from']))`。schema 文档补"detect 窗口＝from 节点进入 tick"不变量。
- **不补的后果**：换故事时跨幕旧消息污染检测，路由提前/重复推进，且加载期 validate 不报错，故障只在运行时表现为诡异路由，无法定位。
- **合并自**：另一条"时间窗跨边累积语义未列入 validate"（见 A-7）是本项的加载期门禁补强，已合并相关动作。

### A-3 [blocker] Phase4 早结束是 watcher 里独立于 apply_routing 的"两段式 LLM 闸门"，无 schema 落点

- **现状**：`watcher.py:141-169` 在 `apply_routing` 之前、edge 循环之外单独跑一条 Phase4 早结束链：`detect_phase4_offer_ending` →（无信号则）`phase4_deal_transcript`（关键词闸＋抓 negotiation_room 最近 16 行）→ `classify_phase4_conclusion` LLM 判 join/seed，命中即写 `ending_id` 并 `pause_world_loop`。dev_logs 仅给 phase4 一个 `early_end: true`，**没有承载：deal 关键词闸、transcript 抓取范围、LLM 结果→edge 转移映射**。
- **为什么是缺口**：这是"f08_director 只产数据不改控制流"与现实的冲突点——`classify_phase4_conclusion` 的输出**直接终结游戏**（写 ending_id + pause loop），是改控制流的。换故事时这条"世界持续跑→谈成了就早结束"分支无配置可表达。
- **补到哪**：dev_logs/42 §2.2（early_end 展开）+ §3 endings/judges + §4 interpreter；dev_logs/43 §2.3 JudgeAgent 红线需修正。
- **具体补什么**：`early_end` 从布尔升格为 `{gate_keywords_ref, transcript:{place, speakers_roles, max_lines}, judge_prompt_ref, result_to_ending:{join_nvidia:..., seed_round:...}}`；interpreter 在遍历 edges 前增"node.early_end 存在则跑 judge→得 ending_id 则走对应 ending 边"的受控钩子；修正 dev_logs/43 表述为"裁判产 (intent/concluded)，由 endings 决策表/early_end 映射决定 ending，仍不凭空造 node/edge"。
- **不补的后果**：早结束分支要么丢失（世界跑飞、永不早结束），要么仍写死在 watcher 代码里（没解耦，换故事必改源码）。

### A-4 [blocker] safe_eval 白名单变量与 session 实际字段不匹配——intent/flags/current_node_id 在 session 上根本不存在

- **现状**：dev_logs/42 §4.3 + endings `when` 用 `intent == 'join_nvidia' and trust >= 25`，safe_eval 白名单声明 `{trust, intent, beats_label, turn, flags}`。但 `HbmSession` 只有 `task_id/start_tick/place_id/phase/player_turn/stats/phase2_start_tick/phase3_start_tick/ending_id`——**没有 intent、没有 flags、没有 current_node_id**；`intent` 只是 `handler.py:191` 当场算出的临时局部变量；`trust` 实际在 `session.stats['trust']` 里。
- **为什么是缺口**：`resolve_ending` 的 `safe_eval(rule['when'], session.vars())` 需要这些字段，但 session 既无 `vars()` 也无这些字段。照 dev_logs 直接落地会 NameError，或 intent 恒取不到（恒 ambiguous→只命中 fallback cold_deal，**join/seed 结局永不可达**），trust==25/15 边界单测无法通过。
- **补到哪**：dev_logs/42 §4.3 + §4.2 resolve_ending；新增 session 字段规约（dev_logs/44 §D 或 §2.2 旁）。
- **具体补什么**：定义 `build_eval_ctx(session, runtime)`：`trust=session.stats['trust']`、`intent=runtime.last_intent`（须把 classify 结果落到 session/runtime 的 `last_intent`）、`turn=session.player_turn`、`beats_label=node.beats_label`、`flags=session.flags`。在 dev_logs 补"session 新增 `current_node_id`/`last_intent`/`flags` 三字段 + `node_start_ticks` dict"的迁移项。
- **不补的后果**：换故事的结局决策表整套不可运行——非崩即恒走 fallback，三个好结局永远到不了。

### A-5 [important] F2F 兜底 NL 路径（escort/Jensen 返回/同室驱逐）schema 不全——detect_node_* 不止 RDC 链

- **现状**：`detect_node_a` 除 RDC 链外有 `_reception_escort_f2f`（受 `require_reception_escort_f2f()` 开关控制）；`detect_node_b` 有 `_jensen_return_f2f`；`detect_node_c` 有 negotiation_room 同室 F2F 驱逐兜底。dev_logs 的 `rdc_chain` 只表达 RDC，**对"F2F 同室关键词"这条并列 OR 兜底没有 trigger 类型**；escort 必需性开关也无落点。
- **为什么是缺口**：换故事若沿用"玩家也能靠当面说话推进"，现 schema 表达不了，会丢失一整类推进方式；escort 必需性无法表达。
- **补到哪**：dev_logs/42 §3 trigger schema + §4.2 TRIGGER_HANDLERS。
- **具体补什么**：新增 `f2f_keyword` trigger `{place, sender_role, keywords_ref}`；允许 `rdc_chain` 增 `require_followup_f2f:{place, sender_role, keywords_ref, optional}` 表达 escort 必需性；node_a/b/c 各补 f2f 兜底；handler 补 `f2f_keyword`。

### A-6 [important] node.agent_behaviors 条件分支（when）schema 仍停留在"建议"级——240+ 行行为卡无法表驱动

- **现状（合并自两条同义缺口）**：`hbm_agent.py` 约 233–356 行的 240+ 行 `if aid==N and phase=='Phase X'` 行为卡，dev_logs/44 §B 落到 `node.agent_behaviors`，但 **未规定 respond_rule/length_rule 如何按"有无未读 RDC / 有无玩家 inject"切换**，也未给 `when` 的字段级 schema、条件键枚举与求值来源（`has_unread_rdc` 从哪算）。§9.3 缺口③至今只是"建议"。
- **为什么是缺口**：没有 `when` 字段定义和求值上下文，WriterAgent 产不出可消费的 agent_behaviors，`build_agent_prompt` 也无法表驱动替换 240 行 if——换故事时这块要么照搬代码要么大段重写 prompt。
- **补到哪**：dev_logs/42 §9.3 缺口③升格为正式 schema 章节；dev_logs/44 §B 字段表。
- **具体补什么**：`agent_behaviors[aid].rules: [{when:{has_unread_rdc?, has_player_inject?, turn_gte?, ...}, respond_rule, length_rule, tool_constraints, keywords_to_watch}]`，按声明顺序首个 `when` 全真者生效；明确求值上下文 `BehaviorCtx{has_unread_rdc(aid), has_player_inject(aid), turn, node_id}` 由 hbm_agent 装配 prompt 时构造；给一个 HBM 完整节点示例（前台 root + Jensen phase2）证明可覆盖旧 if。**必须立"条件键求值表"**（每个键的判定来源），否则仍是空提议。

### A-7 [important] Phase4 inject 的 F07 特例——inject_agents 是运行期开关条件，非静态列表

- **现状**：`routing.py:54-60`：`if phase=='Phase 4' and is_f07_enabled(): return [JENSEN_ID]` 否则 `[2,3]`。dev_logs §3.5 把它落成静态 `phase4.inject_agents:[2]`，表达不了"依 feature 开关二选一"。
- **为什么是缺口**：写死 `[2]` 则 F07 关闭时旧行为 `[2,3]` 丢失，不等价；§3.5 的"可表达性证明"在此并不成立。
- **补到哪**：dev_logs/42 §2.2（inject_agents）+ §3.5 对照表。
- **具体补什么**：`inject_agents:[2,3]` + `inject_agents_overrides:[{when_feature:f07, value:[2]}]`，或把 feature 开关纳入 safe_eval 上下文用表达式选择；§3.5 对照表如实标注此控制点非纯静态。

### A-8 [important] 时间窗跨边累积不变量未列入加载期 validate 或运行期契约

- **现状**：整套推进依赖隐式时序不变量（advance 边写 `to` 节点 start_tick；detect 用 `from` 节点 start_tick 作 `(since_t, t_now]` 下界）。dev_logs 给了读写两侧，但**没把"每条 advance 边必须写 to 节点 start_tick""detect 必须用 from 节点 start_tick"列入 §7 validate 清单**（现 validate 只查无环/root/可达/无死路/rdc_pair⊆allowed/解引用）。
- **为什么是缺口**：生成工具漏写某条边的 start_tick，运行期 detect 退回 `root.start_tick`，跨幕旧消息污染、重复触发或提前推进，**而加载期 validate 不报错**——削弱"validate 通过＝可放心运行"的保证。
- **补到哪**：dev_logs/42 §7 validate 不变量清单 + §4.2 窗口约定。
- **具体补什么**：validate 增不变量"每个有出边且出边含 rdc_*/f2f_keyword/story_signal 的非 root 节点，其所有入边的 `state_updates` 必须写 `node_start_ticks[node]`"；窗口语义写成解释器契约文档，配"跨幕旧消息不应触发新边"的回归单测。

### A-9 [important] ending → pause_world_loop 这个控制副作用在 Story Pack/解释器模型里无落点

- **现状**：`watcher.py:120` bad_end 与 `L154` phase4 早结束命中后都 `pause_world_loop(sim_dir)`。dev_logs interpreter 的 ending 处理只写 `ending_id/game_status; return`，**没有任何地方说到达 ending 要暂停 world_loop**；endings.status 只映射前端展示。
- **为什么是缺口**：剧情模式世界持续运行（commit 4bef65a），到达结局必须停循环否则世界继续推进、画面/状态错乱。换故事时这个副作用若不建模，要么丢失（世界跑飞）要么仍写死在 watcher。
- **补到哪**：dev_logs/42 §4.2 ending 分支 + §3 endings.status 语义；dev_logs/44 运行期流程 ⑧。
- **具体补什么**：interpreter 到达 is_ending 节点时按 `endings[].on_reach:[pause_world_loop]`（或 status＝game_over/completed 隐含）触发受控 loop 控制 action；明确 status 不止映射前端，还驱动 world_loop 生命周期。

### A-10 [nice-to-have] M0 gate 依赖红线 test_r3 与"world_loop 经 abcs 调 interpreter/f08"未对账

- **现状**：`test_r3` 断言 `core/runner/*` 不得 import `f05/f07/f08/f15`；dev_logs/43 §4 要求 world_loop 经 `abcs.py` 受控调 interpreter(f05)/f08_director。dev_logs 只说"要进 abcs"，**没把 test_r3 这条 gate 断言列为必须同步修改/扩展的项**。
- **补到哪**：dev_logs/43 §6 落地步骤 + dev_logs/42 §6 gate 门禁说明。
- **具体补什么**：落地清单显式加"interpreter 入口与 `run_director_judge` 必须经 abcs 导出，core/runner 只 import abcs，同步更新 test_r3 允许/禁止集，新增 abcs 契约单测"；明确 watcher 的 scan_routing 迁入 world_loop 后由谁驱动，避免红线与调用方向冲突。

---

## B. 涌现 feature 与运行期控制（关系/记忆/移动/世界自走）

主线：用户要"涌现社交保留""硬骨架＋自由演员""关系&记忆实时""世界实时变化"。这些能力在引擎里**有实现但无配置出口**，或**只点名没立引擎工作项**。

### B-1 [blocker] relation_types.yaml 缺把 YAML 灌进 type_meta 的引擎接口

- **现状**：`load_from_db` 只从 `RelationTypeRegistrar` 重建 `type_meta`，`seed.py` 从不写，无 yaml 消费者。
- **为什么是缺口**：只补 yaml 没补 ingestion，换故事时 `is_contact`/互斥仍走默认且**静默**——关系语义错了不报错。
- **补到哪**：dev_logs/42 §9.1 / §9.3 缺口2。
- **具体补什么**：新增 `register_types_from_config`，seed 前调用。
- **不补的后果**：换故事的关系图基底错（is_contact 决定 RDC 远端可达），路由会因关系错配而假性失败，且无任何报错。

### B-2 [blocker] on_change hook 只点名没立引擎工作项——确定性兜底永空转

- **现状**：HBM `NullPoolManager` 从不 `register_on_change`，`_fire` 永空转，§9.3 没真列工作项。
- **为什么是缺口**：A→A→B 这类关系迁移全靠 LLM 涌现、无确定性兜底；产品方以为"有护短保证"会被误导。
- **补到哪**：dev_logs/42 §9.3 缺口1。
- **具体补什么**：`kernel.build_kernel` 调 `register_on_change`，定位 parent `set_current_state`。
- **不补的后果**：换故事时关系状态机无确定性兜底，关键关系迁移可能不发生，叙事卡死而看不出原因。

### B-3 [blocker] 自由移动旋钮无表达，dispatch 写死吞 request_move

- **现状**：`hbm_dispatcher.py:65-79` 返回 noop、不读 config；全 dev_logs 无自由移动字段。
- **为什么是缺口**：焊死常量非旋钮，换故事要改源码，无法只换 config——直接违反"硬骨架＋自由演员"。
- **补到哪**：dev_logs/42 §9.3 新增缺口4。
- **具体补什么**：新增 `movement_mode`/`allow_self_move`，dispatch 改读配置。
- **不补的后果**：想要"演员自由走动"的新故事根本配不出来，只能改源码。

### B-4 [important] f08_director 触发点未精确到挂点（评分频率/world_step 哪行/与 resolve_ending 次序）

- **现状**：输入输出已定义，但触发点模糊——没给评分频率、world_step 哪一行、与 resolve_ending 的次序。
- **为什么是缺口**：次序错（resolve_ending 读到旧 trust 翻车）、频率错（stats 全空）。
- **补到哪**：dev_logs/43 §5.1 或 dev_logs/44 §3 补次序表。
- **具体补什么**：定 world_step 顺序"f08 写 trust → resolve_ending 读"，并明确每 world tick 还是每 player_turn 评分。

### B-5 [important] "世界不停变化"缺非 turn 驱动的常驻循环配置

- **现状**：`timed_events` 键全是 `turn=16`；f18（4bef65a）世界 tick 自走但无 schema 字段。
- **为什么是缺口**：`timed_events` 是玩家回合一次性注入、非世界自走；f18 有实现无配置出口。
- **补到哪**：dev_logs/42 §3 timed_events schema。
- **具体补什么**：加 `every_ticks`/`at_tick`/`recurring`，挂 `world_loop.tick`。

### B-6 [important] 世界自走 tick 与玩家 turn 两套时序的交互未定义（次序/并发/锁）

- **现状**：`world_loop.py` 有常驻 asyncio `_loop` + `_cycle_lock` + `_pause_event`，世界按 tick 自走；f02 player_turn 是玩家驱动回合。dev_logs/44 把①输入→⑥路由→⑦裁判→⑧结局画成线性 turn 链，**没说 world tick 与 player_turn 谁触发 apply_routing/resolve_ending、并发如何加锁、裁判/结局每 turn 还是每 tick 跑**。
- **为什么是缺口**：(1) 世界自走期间达成的 rdc_chain，路由若只挂 player_turn 会漏判；(2) 自走期间达成的结局（agent 自发谈成）若只在 player_turn 判则不触发，与现状 watcher 在 loop 里判早结束矛盾；(3) `_cycle_lock` 与 player_turn 的并发边界没进数据驱动模型，换故事会丢失或写死。
- **补到哪**：dev_logs/44 §3 新增"世界自走 tick 与玩家 turn 的时序契约"；dev_logs/42 §4.2 明确触发时机。
- **具体补什么**：(a) apply_routing 在"每个 world tick 末"评估（覆盖自走推进）；(b) resolve_ending/早结束同样挂 world tick，与 player_turn 互斥；(c) 玩家输入入队、loop 在锁内串行消费；(d) interpreter 契约声明"路由是 tick 驱动而非 turn 驱动"，配回归。

### B-7 [nice-to-have] 三旋钮无统一聚合层与一致性校验

- **现状**：硬骨架已配齐，agent_behaviors 未细化，自由移动无落点，无 `control_profile`。
- **为什么是缺口**：缺聚合层会配出非法组合（free 但 active_agents 空）而无 validate。
- **补到哪**：dev_logs/42 §3 story_graph metadata。
- **具体补什么**：加 `control_profile=skeleton/guided/sandbox` + validate 校验组合合法性。

---

## C. 运维生命周期、迁移、测试与健壮性

主线：Story Pack 是"碟片"、引擎是"播放器"。碟片如何被加载、校验、隔离、版本化、回归、回退——这套生命周期当前大量是文档约定而非机制。

### C-1 [blocker] 真实播种入口是 Runner 的 build_kernel，dev_logs 把 load→validate→seed 全画在 Flask /session

- **现状**：dev_logs/44 把 `load_story_pack→validate()→失败 400→seed_world` 全画在 Flask `routes.py POST /session{story_id}`。但真实播种在 **Runner 进程**：`run_hbm.py:160 load_scenario → build_kernel → kernel.py:152 seed_world`；`--config/--sim_dir` 是两个独立 CLI 参数、无 story_id 概念；`routes.py:session_start` 只 `create_session()`、写死 `SIM_ID==hbm_memory_war`、根本不 seed。全仓 0 处 story_id/load_story_pack/pack.validate。
- **为什么是缺口**：validate 真正要保护的 `seed_world` 在另一个进程、且早于任何 Flask 请求就已 seed 完。照现描述实现会出现"Flask 校验通过但 Runner 用的是另一份/旧 scenario"或"Runner 拿坏包直接 crash、Flask 永远等不到健康进程"。
- **补到哪**：dev_logs/44 §2 重写（validate 必须在 Runner `build_kernel` 之前跑，Flask 的 400 来自回读 Runner 启动失败/env_status）；dev_logs/42 §5 逐文件清单为 run_hbm.py 增改造项。
- **具体补什么**：`run_hbm.py:main` 把 `load_scenario` 改 `load_story_pack(story_id)` 并在 build_kernel 前 `pack.validate()`，失败 `write_env_status(status='invalid_pack', error=...)` 退非零；`routes.py:session_start` 读 env_status，invalid_pack 返回 400 带报告；`paths.py` 新增 `get_story_pack_dir(story_id)`，把 `--config/--sim_dir` 收敛为单一 story_id。
- **不补的后果**：换故事时校验形同虚设，坏包绕过 Flask 在 Runner 直接崩，前端拿不到任何可读错误。

### C-2 [blocker] 未规划把现有 HBM 抽成第一个参考 Story Pack 并作永久回归锚点

- **现状**：dev_logs 把 HBM 的 `story_graph.yaml` 当"重构期一次性等价证明"，**没要求**把完整 `config/stories/hbm_memory_war/`（18 YAML）作为长期 checked-in 资产持续回归；阶段二验收闭环反而新造 `min_demo` 当样例。`config/stories/` 目录现不存在。
- **为什么是缺口**：(1) 拆 `hbm_scenario.yaml`（relations/capabilities/coverage/agents soul）成 18 YAML 时字段漂移无对照基线；(2) 解释器后续迭代缺一个"已知正确的真实故事"做持续回归（min_demo 是简化换皮，覆盖不到 HBM 全部 16 控制点）；(3) HBM 长期半留 scenario 半留代码，新旧双真值源并存。
- **补到哪**：dev_logs/42 §6 阶段二 + §7、dev_logs/43 §6.2 Step0：新增"产出并 commit `config/stories/hbm_memory_war/` 完整 18 YAML，优先于 min_demo"。
- **具体补什么**：全量拆 `hbm_scenario.yaml + story_knowledge/` 成 18 YAML 并 checked-in；gate 加回归：此包 `enumerate_all_paths()` 断言 join/seed/cold/bad 四路径恒在，且 `seed_world(此包)` 与现 scenario 播种逐表 diff==空；删 scenario 顶层世界原语双真值源。
- **不补的后果**：拆包无损与否无法判定，HBM 这唯一真实故事会在迁移中悄悄漂移，且后续所有解释器改动失去回归锚点。

### C-3 [blocker] 缺"为任意 Story Pack 做验收"的通用 gate——test_m0 把 HBM 常量写死在 200+ 断言里

- **现状**：gate＝`test_m0.py`（4405 行）约 37 个结构单测 + e2e + npm build，断言体写死 `"nvidia_reception"`、`inject_agent_ids_for_phase("Phase 1")==[1]`、`trust>=25`、四地点、resolve_ending 边界等。无 `pack.validate()` 门禁测试、无 `enumerate_all_paths` 路径回归、无第二故事样例。
- **为什么是缺口**：换任意 Story Pack 时 (1) 没有通用 validate gate 判该包合法（无环/root/结局可达/无死路/RDC 对子集/role·place·agent·relation·capability 解引用——dev_logs/44 §D 列为"实现度 0"）；(2) test_m0 现有断言因 story_id 变化大面积失效，无"按 story_id 读期望值"的参数化夹具。
- **补到哪**：dev_logs/42 §7 + §6；hbm_demo/CLAUDE.md gate 章节改"参数化 gate"。
- **具体补什么**：新建 `scripts/tests/test_story_pack.py`（与 test_m0 并列）：入参 story_id，三类断言——(a) `load_story_pack(id).validate()` 必过，对故意坏包（造环/不可达结局/悬空 rdc_chain/未知 role）断言抛 ValidationError；(b) `enumerate_all_paths()` 断言每个声明 ending 都 root-可达；(c) seed_world 后各表非空且引用闭合。test_m0 写死的 HBM 常量改为从 `load_story_pack('hbm_memory_war')` 读的夹具值。gate 跑 hbm_memory_war + min_demo 两个 id。
- **不补的后果**："只改 config 换故事"无可执行验收，换任意新故事时自身断言全红，坏包无加载期门禁拦截。

### C-4 [blocker] 安全红线"生成工具不得写用户 playthrough 库"只有文档约定，缺强制隔离机制

- **现状**：dev_logs 反复声明 authoring "永不碰 world_state"，但 authoring（story_authoring/，未落地）与运行期共享同一 Python 包，能 import `seed_world/WorldDB`；`config/stories/<id>/`（authoring 输出）与 `sim/<id>/world.db`（playthrough）无代码级隔离或权限护栏。
- **为什么是缺口**：红线靠"开发者自觉不 import"维持，无法防止 authoring 误写/覆盖正在运行的玩家存档：(1) 同进程权限、共享 paths.py，一行 `get_world_db_path()` 即可碰 playthrough；(2) 命名空间混用时"重新生成"可能覆盖玩家 world.db；(3) 无"authoring 只许写 config/stories/、禁止写 sim/"的运行期断言。
- **补到哪**：dev_logs/43 §6.1 目录结构 + dev_logs/44 §4 分层表；hbm_demo/CLAUDE.md 安全红线章节同步加一条。
- **具体补什么**：story_authoring/ 只许 import "写 config" 接口与 `StoryGraph.validate()`，**禁止 import seed/kernel/WorldDB**（用分层依赖红线测试断言，类比 test_r3）；输出根固定 `config/stories/`、加运行期断言"输出路径不得在 sim/ 下"；两目录物理分离、authoring 对 sim/ 无写权限。gate 加红线测试：断言 story_authoring 模块 import 图不含 `seed_world/WorldDB`。
- **不补的后果**：用户点名的安全红线只是"文档红线"，一次 authoring bug 即可覆盖正在游玩的存档，不可逆数据损失。

### C-5 [important] Story Pack 无 schema 版本号/兼容性策略——schema 演进会静默错配

- **现状**：全文 0 处 `schema_version`；meta.yaml 只有 story_id/root_node_id/simulation_id/timeline；`load_scenario` 仅 `yaml.safe_load`、零 schema 校验。
- **为什么是缺口**：碟片没刻版本号。schema 演进时旧包配新解释器或新包配旧 Runner 会"字段被静默忽略"或运行期 KeyError，无法在加载期给"包版本 vX 不被本引擎接受"的明确报错；authoring 产包也无法标注针对哪个版本。
- **补到哪**：dev_logs/42 §3 meta.yaml + §7、dev_logs/44 §D 兼容性矩阵。
- **具体补什么**：meta.yaml 加 `schema_version`；`load_story_pack` 在 validate 第一步比对 `SUPPORTED_SCHEMA_VERSIONS`，不匹配 raise；authoring 产包写入当前版本；gate 增"缺版本/版本越界"拒绝用例。

### C-6 [important] 校验失败/字段缺失的统一策略缺失（fail-fast vs 降级 + 错误聚合）

- **现状**：§8 风险表给了零散兜底（行为卡缺字段→默认；safe_eval 错→硬编码结局；unknown role/place→拒绝启动），但**互相矛盾**（有的拒绝、有的降级），无字段级 required/optional 清单，未规定首错即抛还是聚合上报。`seed.py` 对缺字段是裸下标 `p["place_id"]`/`int(a["agent_id"])` 直接 KeyError 崩。
- **为什么是缺口**：换故事配置必有疏漏。同类缺失行为不一致难预期；"降级到默认行为"对叙事是危险的（行为卡缺字段降级成默认，演员行为全错但游戏照跑）。
- **补到哪**：dev_logs/42 §3 各 schema 处标 required/optional+default；§8 上方新增"校验失败统一策略"。
- **具体补什么**：18 YAML 每字段标 required/optional(default)；`pack.validate()` 聚合返回 `List[ValidationError]` 一次性报；定义红线字段集（story_graph 的 nodes/edges/root、endings 的 fallback、agents 的 roles）缺失一律拒绝启动，非红线字段走文档化默认；seed.py 裸下标改 `.get` + 加载期 dry-run。

### C-7 [important] 多故事并存与运行期切换无机制——config/stories/<id> 与 sim/<id>/world.db 关系未定义

- **现状**：`--sim_dir`/`--config` 独立二参，`paths.py:get_sim_dir` 只读环境变量、`DEFAULT_CONFIG` 永指 scenario。dev_logs/44 §D 只一句"paths.py 按 story_id 返回 config/stories/<id>/"，**没说 playthrough 的 `sim/<id>/world.db` 如何随 story_id 切、两故事存档是否并存、运行中能否热切**。
- **为什么是缺口**：配置包路径与 playthrough 路径是两套命名空间，dev_logs 只处理前者。(1) 切故事不清 sim_dir 会让新故事 seed 写进旧 world.db；(2) 多故事并存存档互相覆盖；(3) Runner 单进程单 sim_dir 常驻，"运行期切故事"实际是"换 sim_dir 重启 Runner"，与 dev_logs"Flask 请求即可切"矛盾。
- **补到哪**：dev_logs/44 §D + §2 补"playthrough 隔离与多故事并存"。
- **具体补什么**：`paths.py` 新增 `get_playthrough_dir(story_id)=sim/<story_id>/`，与 config 一一对应但物理分离；规定切故事＝"换 story_id 重启 Runner 指向新 sim_dir"（非请求内热切）；"同一 story_id 的 world.db 即该故事存档"，多故事各自并存；§2 流程图标注"切故事＝Runner 重启"。

### C-8 [important] ui_text/语言风格随 session 下发通道实现度 0，且无"下发 payload 与 story_graph 一致性"校验

- **现状**：dev_logs 规划 session 初始化把前端可见子集编译 JSON 随 `/scenario` 下发，但 routes.py 现无此实现，前端 `constants/*.ts` 仍静态 import 中文常量；language_style 下发只在文档；§8 风险表提"E2E 校验下发 ui_text 与 story_graph 一致"但无落点。
- **为什么是缺口**："前后端零 diff 换故事"的最后一公里是 ui_text 下发，0 实现且无验收：(1) 换故事后前端仍显旧 HBM 角色名/地点/结局；(2) ui_text 是 story_graph 派生子集，缺一致性校验会漂移（前端显示 Jensen 但后端已换人）；(3) language_style 不下发则"大白话/禁用术语"约束只在后端生效。
- **补到哪**：dev_logs/44 §2 + §D；dev_logs/42 §6 阶段四 E2E 断言。
- **具体补什么**：routes.py 实装 `GET /scenario` 返回由 `load_story_pack(id)` 编译的 ui_text JSON；前端 `StoryConfigContext` 注入、`constants/*` 改读 store；`pack.validate()` 增"ui_text.agents/places/endings ⊆ story_graph/endings 声明集"一致性校验；gate 加 E2E：换占位 ui_text 后前端零改一行呈现新文案。

### C-9 [important] "世界原语 seed 迁移"无分阶段顺序与里程碑——最危险的不可逆 seed 改写被悬空

- **现状**：§6 四阶段（抽字符串/抽路由/抽结局裁判/前端文案）全是叙事控制流，无一行提 relations/seed/world.db。但真正改 `seed_world()` 的大头在 §9 + §44 §A：拆 relations/capabilities/coverage/agents soul 并改 `seed.py`。`seed.py` 裸下标、`kernel.py:152 seed_world`、`world_reset.py:_restore_agents_from_scenario` 还直接读 scenario dict 取 soul/goal/state——这条独立迁移链没排进阶段路线。
- **为什么是缺口**：`seed_world()` 改写最不可逆、最易静默错配（播种错了整局世界基底就错，且不像路由有 v2 开关）；它与阶段二有强顺序依赖——路由的 rdc_chain 依赖 relations/relation_types 已正确播种，若先上路由后迁 seed，阶段二回归会因关系图错配假性失败，无法定位是路由 bug 还是 seed bug。
- **补到哪**：dev_logs/42 §6：在阶段二之前新增"阶段零·世界原语拆包与 seed 改写"，给里程碑（逐表 diff==空）+ 顺序依赖声明；dev_logs/44 §A 表加"所属迁移阶段"列。
- **具体补什么**：(1) 拆世界原语块→relations/relation_types/places(coverage)/agents.yaml；(2) seed.py 改读 Story Pack + `register_types_from_config` 先灌 type_meta；(3) `world_reset.py:_restore_agents_from_scenario` 同步改读 agents.yaml（否则 reset 后 soul 仍来自旧 scenario，双真值源）；(4) 里程碑：`seed_world(新包)` 与 `seed_world(旧 scenario)` 对 place/coverage/capability/relation/agent_location 五表逐行 diff==空才算过，且必须在阶段二之前合入。
- **不补的后果**：seed 改写若在路由迁移后做，关系图错配会让整条路由回归假性失败、无法归因；这是 blocker 级风险，本身列 blocker。
- **严重度修订**：本项原 dimension 标"完备性批评"，按后果应视为 **blocker**。

### C-10 [important] 路由/裁判/结局的运行期可观测性（trace）缺位

- **现状**：`f15_prompt_trace` 只 trace 演员 agent 提示词且以 phase 字符串为键。表驱动解释器换边、resolve_ending、f08 裁判判定全程无 trace；dev_logs 只在 §7 提"录制裁判输入输出做回归数据集"（离线，非运行期 in-band trace）。
- **为什么是缺口**：换故事后世界跑飞/结局判错/卡节点，没有"为什么走这条边/为什么选这个结局/裁判看到了什么"的 trace，只能人肉读 world.db 反推；且 phase 降级为 beats_label（可重复/可空）后 trace 键会失真。表驱动把控制流从可读 if 变成数据 dispatch，**更**需要 trace。
- **补到哪**：dev_logs/42 §4.2（apply_routing/resolve_ending 增 trace 钩子）+ dev_logs/43 §2.2（裁判输入输出落 trace）；trace 键 phase→node_id/edge_id。
- **具体补什么**：interpreter 每次评估边写 `{tick, from_node, evaluated_edges:[{edge_id, trigger_kind, detected, window_since}], chosen_edge, actions_applied}`；resolve_ending 写 `{rules_evaluated, chosen_ending, fallback_used}`；裁判写 `{judge_point, llm_input_digest, raw_output, parsed_intent}`；gate 加"跑完一局能从 trace 重建实际走了哪条路径 + 每步换边理由"。

### C-11 [important] "逐帧等价回归"依赖的 snapshot 录制/比对 harness 本身没规划

- **现状**：§6 各阶段 + §8 反复把验收写成"snapshot 逐帧/逐 turn 对齐"，但源码只有 `reset_world_runtime`（清表重 seed＝重开），无 snapshot 接口。双跑＋逐帧 diff harness（怎么在新旧两条路由各跑一局、逐 turn dump world.db、结构化 diff、忽略哪些非确定字段）完全无设计落点。
- **为什么是缺口**："逐帧等价"是 dev_logs/43 §7 自定的硬门槛，但实现它的工具从未规划成工作项——没有 harness 等价性退化成"看起来差不多"；且演员对白 LLM 非确定，diff 必须明确比对哪些表、忽略哪些，否则每次因对白不同假性失败。
- **补到哪**：dev_logs/42 §6 阶段一前置 或 §7；dev_logs/43 §6.2 Step0 展开。
- **具体补什么**：规划 replay-diff harness：固定玩家输入序列→old/new 两路各回放→每 turn dump 决定性子集（current_node_id 转移、inject 目标、agent_location、relation 变化、ending_id）→结构化 diff，显式忽略集＝演员对白/trace/时间戳；diff==空才算等价。先建 harness 再迁路由。

### C-12 [important] f18_scene_render 运行期渲染器源码在工作树缺失（只剩 __pycache__），却被运行期⑨与设计期 Artist 同时当复用基座

- **现状**：本分支最近 5 commit 都是 f18 出图；dev_logs/44 运行期⑨依赖 f18 实时出图；设计期 Artist（见 D-7）也提议复用 f18 抽象。但 `f18_scene_render` 的 `.py` 在工作树缺失（git ls-files 为空，仅 __pycache__ 显示 client/config/consistency/prompt_builder/render/store 结构）。
- **为什么是缺口**：(1) 任何人 checkout 本分支拿不到 f18 源码，出图链路不可落地/不可回归；(2) 设计期 Artist 复用一个不在工作树的模块＝空中楼阁；(3) 出图是有成本/延迟/可能失败的外部调用，却无源码可审其重试/超时/降级，也无 trace。
- **补到哪**：dev_logs/44 运行期⑨ + ArtistStep：先补"f18_scene_render 源码归位/重建为可见模块"前置项。
- **具体补什么**：(1) 把 f18 源码恢复进版本控制（确认是否被 gitignore/漏 add）；(2) 显式声明 f18 失败/超时/降级策略（出图失败时世界继续跑、用占位图、写 trace）与成本（每帧 1 次×连续并发＝每 turn 多少张）；(3) 复用前提是 f18 抽象在工作树可见且接口稳定。

### C-13 [nice-to-have] 运行中世界的存档/恢复缺失（只有 reset 重 seed，无 snapshot→restore）

- **现状**：`reset_world_runtime` 是清表重 seed＝"重开"非"读档"；全仓无 save/load/snapshot/checkpoint；dev_logs 未涉及。
- **为什么是缺口**：(1) 世界持续运行，玩家中途退出再回来无法续档；(2) 裁判 eval 回放缺"固定 world 快照"做确定性输入；(3) schema/解释器升级后旧 playthrough 能否恢复无迁移路径。
- **补到哪**：dev_logs/44 §3 新增"playthrough 存档/恢复"（引擎能力，非 Story Pack 数据）。
- **具体补什么**：`snapshot_world(world_db, tick)->snapshot_id` 与 `restore_world(snapshot_id)`；session 记录 `last_snapshot` 续档；存档与 schema_version 绑定，跨版本恢复先兼容检查。

### C-14 [nice-to-have] schema 演进后旧 Story Pack 的迁移（migration）无路径

- **现状**：版本号（C-5）只解决"拒绝旧包"，没解决"升级旧包"；全文 0 处 migration/upgrade。authoring 批量产 v1 包后，schema 演进会让历史包既被版本号拒绝、又无自动升级路径，只能逐包手改或整包重生（重烧 LLM/出图成本）。
- **补到哪**：dev_logs/42 §3 meta.yaml 旁 或 dev_logs/44 §D。
- **具体补什么**：每次破坏性演进配 `migrate_pack_vN_to_vN+1(pack)->pack` 确定性转换器（纯数据、不调 LLM）；story_authoring 提供 `upgrade <id>` 批量升级并重跑 validate；加载期遇旧版本先尝试 migrate 再校验；明确哪些可纯迁移、哪些必须重生。

---

## D. 设计期生成流水线（用户只写剧情 → 管理 agent 生成 → validate → 微调）

主线：用户的诉求是"只写剧情，由管理 agent 工作室生成 Story Pack"。这条流水线当前几乎全是散文描述，缺输入契约、中间产物 schema、回路机制、人审入口、增量重生、可测试性、成本预算。对标物是 AI4VN（input.yaml 契约、call_json_with_schema、WorkflowController 有界回路、幂等落盘、Artist 一致性链）。

### D-1 [blocker] 用户输入的 story brief 没有任何格式规范

- **现状**：dev_logs 把 Designer 输入写成"故事需求文本、角色数、期望幕数"一句话，§44 §1 给一段示范散文。全仓 grep `brief`/`输入格式` = 0。对比 AI4VN 有显式 `input.yaml` 契约：`requirements.file_path` 指向纯文本世界观（可空→AI 自由发挥）+ 可选结构化 `oc.characters[]`（空字段 AI 补、已填锁定）。
- **为什么是缺口**：没有输入契约，生成的第一道门就模糊——Designer 拿到的可能是一句话也可能一篇设定集，无法判定"角色数/幕数/玩家身份/结局数/锁定 OC"这些驱动 DAG 规模的关键参数从哪来；HBM 的强约束（外来访客、7 角色固定阵营、4 幕、3+1 结局）若不结构化，LLM 抽取必然漂移（§43 §风险自认"难从一句话稳定抽取"），也支持不了"锁定我已写好的主角"。
- **补到哪**：dev_logs/44 第一部分新增"设计期输入契约（story brief schema）"，或 dev_logs/43 §2.2 前补 brief 字段表；story_authoring/ 新增 brief 模板文件。
- **具体补什么**：`story_brief.yaml`：`premise`（自由文本，可空）、`player{identity, role, is_outsider}`、`target_acts`（幕数/节点数提示）、`characters[]{name?, faction?, is_protagonist?, personality?, appearance?, locked:bool}`（对标 AI4VN，locked 控制 AI 可否改写）、`endings_spec[]{id, condition_hint}`、`art_style_hint`、`language_style_hint`；明确"空字段 AI 补全 / locked 字段冻结"规则。
- **不补的后果**：生成流水线入口无契约，换故事时管理 agent 抽不出稳定参数，DAG 规模随机漂移，"锁定我的主角"诉求无法实现。

### D-2 [blocker] 三个管理 agent（Designer/Producer/Writer）无字段级 JSON schema 契约，无法做"生成+校验+重试"

- **现状（合并自两条同义缺口）**：契约表每个 agent 只有一行自然语言输入/输出，全仓无 `GAME_OUTLINE_SCHEMA`/`STORY_GRAPH_SCHEMA`/`PLOT_SEGMENTS_SCHEMA`。对比 AI4VN 每个 agent 输出都过 `call_json_with_schema`（生成→校验→失败回灌错误重试一次→仍失败 raise），schema 显式定义在 schemas.py。
- **为什么是缺口**：没有中间产物 schema，"Plan→Review→Revise"循环缺底座——Producer 拿到 Designer 输出无法机器校验，Writer 拿到 DAG+权限也无契约。dev_logs 自己点名要抄 `call_json_with_schema` 但没把 Designer 半成品、Producer 校验报告定 schema。
- **补到哪**：dev_logs/44 第一部分新增"生成期中间产物契约"（区别于运行期 Story Pack schema）；story_authoring/ 新增 `authoring_schemas.py`。
- **具体补什么**：`DesignerOutput{nodes[]{id,beats_label,node_type}, edges[]{from,to,trigger_hint}}`（不含权限）；`ProducerReport{is_valid, errors[], node_permissions{node_id:{active,passive,frozen,inject,allowed_rdc_pairs,player_place}}}`；`WriterInput=DesignerOutput+ProducerReport`。每个 agent 走"call_json_with_schema 式生成→校验→重试一次"；明确这些是生成期临时契约，最终冻结为运行期 Story Pack（二者 schema 不同）。
- **不补的后果**：生成期多 agent 协作字段漂移无拦截，无法机器校验，"工作室生成"退化成不可靠的一次性 LLM 大喷。

### D-3 [blocker] validate 失败 → 重生成的回路完全没有设计

- **现状**：对回路只有一句"三角色走 Plan→Review→Revise，直到 validate() 通过才冻结"。全仓 grep 重生成/回路 = 0。`StoryGraph.validate` 只是运行期加载门禁（失败 raise / 400），不是生成期回路。对比 AI4VN 回路极完整：`_review_and_revise` Producer critique→不过则 Designer 带 feedback 重生→最多 3 轮→超限强制放行（不死循环）；schema 失败也回灌重试一次。
- **为什么是缺口**："循环到 validate 通过"是结果断言不是机制。缺回路三要素（最大次数 + 超限放行 + feedback 结构化回灌），实现时只有两种坏结局：validate 失败直接 raise 卡死（无重试），或无限循环（LLM 反复产不合法 DAG）。
- **补到哪**：dev_logs/44 第一部分新增"生成期校验-重生成回路"；落到 story_authoring/ orchestrator（对标 WorkflowController，而非塞进某 agent）。
- **具体补什么**：Producer.critique 返回 PASS 或结构化 feedback（哪些节点不可达/哪条边 rdc_chain 越界）→不过则把 feedback 合并进 Designer/Writer prompt 重生→最多 N 轮（建议 3，可配）→超限时"强制放行+标记 needs_human 或 raise 给人工"（明确选哪个）；失败产物归档 story_authoring/logs/；明确生成期回路（产 YAML）与运行期加载门禁 validate()（返回 400）是两层不同 validate。
- **不补的后果**：换故事生成要么卡死要么死循环烧钱，工作室流水线根本跑不通。

### D-4 [blocker] 设计期 assets 生成（Artist 步骤）整段缺失，且 f18 运行期实时帧与设计期静态资源被混淆

- **现状**：hbm_demo 子树 grep tapnow/seedream/Artist/美术 = 0；dev_logs 里 assets/ 只作目录名出现两次，无生成步骤。dev_logs/44 把 AIGC 出图只画在运行期⑨（world_delta→实时出图），设计期 assets/（静态背景/头像）来源完全空白。f18_scene_render 是运行期实时帧渲染器，与 AI4VN artist_agent 同构但用途不同。§6 分阶段路线里根本没有"生成 assets"阶段。
- **为什么是缺口**：流水线宣称产物含 assets/，但没有任何 agent/步骤负责产它，也没说复用 f18 还是新写。把"运行期实时帧"和"设计期静态背景/头像"混为一件事，会导致：要么设计期根本不出静态资源（运行期每帧重画，无稳定头像/背景），要么重复造轮子。AI4VN 的 Artist 步骤（背景→立绘按表情→封面；一致性靠风格基准图；白底+rembg 抠图；幂等落盘）是现成蓝图，dev_logs 完全没引用。
- **补到哪**：dev_logs/44 第二部分"设计期"补 ArtistStep / story_authoring 新增 asset 子模块；dev_logs/42 §6 补"阶段五：设计期静态资源生成"。
- **具体补什么**：新增设计期 Artist 步骤（离线、放 story_authoring/、绝不进 Flask 运行时）：读 agents/places/ui_text → 复用 f18 的 client/prompt_builder/consistency 抽象按 AI4VN 顺序产 assets/：背景（无人、横版）→头像/立绘（纯底、按表情维度）→封面；一致性用"先定一张风格基准图，后续以它为参考+文字约束差异"；白底+抠图；以角色 id/地点 id 为稳定文件名幂等落盘（存在即跳过，支持局部重生）；产物路径写进 `ui_text.assets`。明确区分 f18＝运行期实时帧（进 Runner）、此 Artist＝设计期静态资源（离线 authoring），可共享 prompt/consistency 代码但生命周期不同。
- **不补的后果**：换故事时没有新世界的稳定背景/头像，前端要么显示旧 HBM 资产要么无图，"画面体现新世界"兑现不了。

### D-5 [important] "用户微调"（流水线第四环）无任何落地设计

- **现状**：任务把"用户微调"列为终点，但 dev_logs 里 grep 微调仅 2 命中且都指运行期；grep 人审 = 0；仅一句"管理者 LLM 只做草稿+人工校对""初版手写 YAML / 向导 UI 辅助"，无入口/流程/字段。AI4VN 没有人审 UI，这块是 hbm_demo 从零设计。
- **为什么是缺口**：流水线宣称"生成→validate→微调"，但微调零设计意味着用户拿到 18 个 YAML 后要直接手改裸 YAML（无引导、无字段说明、改完不知会不会破坏 validate 不变量），或根本没有回工具的通道。dev_logs 把"手写 YAML"和"LLM 生成后微调"混为一谈，回避了"LLM 生成 + 人审修正"这个真实主路径的交互设计。
- **补到哪**：dev_logs/44 第二部分"设计期"流程补"人审/微调子步骤"；story_authoring/ 新增 CLI 子命令或 review 模式。
- **具体补什么**：(a) story_authoring CLI 增 `review`——生成后 dump 人类可读 diff/摘要（节点图 ascii + 各节点权限表 + 四结局路径 `enumerate_all_paths` 列表）供核对；(b) 用户编辑 brief 或直接编辑 YAML 后跑 `validate <id>` 重过加载期 validate 并报告违反的具体不变量；(c) 明确微调粒度——改 brief 重生还是直接改 YAML；若直接改 YAML 必须强制重跑 validate 才能标 frozen。

### D-6 [important] "部分重生成"（只改一个节点不全盘推倒）完全没有设计

- **现状**：grep 部分/局部重生/增量生成 无相关设计；dev_logs 强调"产物一次性冻结""冻结后不可动态改流向"。对比 AI4VN 天然支持局部重生：阶段间靠文件+schema 解耦、下游靠"文件已存在则跳过"幂等；立绘审图回路是"只补失败的那张"；script 阶段 DAG 拓扑分层并发、单节点失败不阻塞全层。
- **为什么是缺口**：没有局部重生，用户微调体验极差——只想改第 3 幕一个触发条件或某角色 soul，却要把整个 Story Pack 推倒重生（含已满意节点、已生成 assets），既慢又引入新不一致。这与"用户微调"直接冲突（微调本质就是局部修改）。
- **补到哪**：dev_logs/44 第一部分新增"局部/增量重生成与幂等"；story_authoring/ orchestrator 规划幂等策略。
- **具体补什么**：以 node_id / agent_role / 文件名为稳定 key，"产物已存在且无修改请求则跳过"；支持 `regenerate --node <id> / --agent <role> / --file <name>` 局部重生，只重产指定切片并重跑 validate，其余原样保留；assets 同理（角色 id-表情名为 key，只补缺失）；明确哪些改动强制级联重生（改 edges 必重跑全图 validate，但不必重生 agents.yaml）。

### D-7 [important] 生成期工具自身的确定性/可测试性是盲区

- **现状**：dev_logs 的"确定性""可复现""enumerate_all_paths"全针对运行期解释器；生成期工具（Designer/Writer LLM）的"同一 brief 是否产同一 Story Pack""生成结果如何回归测试"完全没提；gate(test_m0) 是"HBM 这一个故事"验收，无 story-authoring 测试。
- **为什么是缺口**：生成工具 LLM 驱动天然非确定。不设计固定 seed/低 temperature/录制-回放 fixture/schema 校验作 CI 断言，则 (1) 同一 brief 两次生成出不同包无法回归；(2) 无法在 CI 验证"改了 prompt 后仍能产出合法 Story Pack"——整条流水线入口端不可测，与运行期严密可回归形成断层。
- **补到哪**：dev_logs/44 新增"生成期工具的可测试性"；story_authoring/ 规划 tests/ 与 CI 钩子。
- **具体补什么**：(a) LLM 调用低 temperature(0.1–0.3)+ 可注入 seed；(b) 录制 brief→Story Pack 的 fixture，CI 用 eval 模式读预录不真调 LLM；(c) 核心断言不依赖 LLM 文本逐字一致，而断言"产物过 validate() + enumerate_all_paths 命中预期结局集 + 节点数符合 brief.target_acts"——把生成正确性归约到确定性 schema/图断言。

### D-8 [important] 生成期成本/性能/配额完全无预算（用户点名要算）

- **现状**：dev_logs §43 §3.1 只量化运行期成本（路由 0 新增 LLM、导演 2-3 次/session）。生成期是 LLM 密集的：三 agent × Plan-Review-Revise 最多 N 轮 × 每轮 call_json_with_schema 生成+重试，再叠加 Artist（背景+每角色每表情立绘+封面+审图回路）。全文对"生成一个完整 Story Pack 端到端要多少次 LLM、多少 token、多长时间、多少钱"0 量化、0 预算上限、0 配额/限流。
- **为什么是缺口**：生成期才是 LLM/出图成本的真正大头（立绘按表情×角色数线性放大），却没算：(1) 无法判定一次生成是 30s 还是 30min、$0.5 还是 $50；(2) 无预算上限与限流，回路反复重试+大量出图会失控烧钱/超时；(3) `POST /scenario` 触发后台生成若无超时/配额，多用户并发会拖垮 LLM 配额。
- **补到哪**：dev_logs/43 §3 新增"生成期成本预算"（与运行期并列）；dev_logs/44 authoring 章节补"单次生成 LLM 调用预算表 + 超时/配额"。
- **具体补什么**：给出预算表：每 agent 调用次数上界（Designer 1 + Producer N + Writer 1 + 回路重试上限）、Artist 出图次数＝背景数+Σ(角色×表情)+封面、估算 token/张数→时间与费用区间；orchestrator 设硬上限（max LLM calls / max images / 总超时），超限即停并报告；`POST /scenario` 后台任务加全局并发配额与每用户限流；CI 用预录 fixture 避免回归真烧钱。

### D-9 [important] 工具内部"编排器 vs agent 分离"与 CLI 命令面无落地规约

- **现状**：dev_logs 已明确落点（独立离线工具 story_authoring/ 或 scripts/ CLI，永不碰 world_state，POST /scenario 只触发不同步执行）——这层定位清楚（非缺口）。但 story_authoring 内部没规划"编排器（对标 WorkflowController，只做编排/落盘/回路控制）与 3 个 agent（只管单一 LLM 能力）分离"；也没 CLI 命令面（generate/validate/review/regenerate）。story_authoring/ 目录现不存在，实现度 0。
- **为什么是缺口**：落点对了但"工具内部怎么组织"缺规约，容易把回路控制/落盘塞进某 agent（AI4VN 明确编排器≠agent）；CLI 命令面没定，则前述缺口（D-3 回路 / D-5 人审 / D-6 局部重生）无统一入口承载。
- **补到哪**：dev_logs/44 或新开文档，规划 story_authoring/ 模块结构与 CLI；对标 AI4VN workflow.py + `--mode` 多阶段独立可重入。
- **具体补什么**：`orchestrator.py`（管回路+落盘+幂等，不含 LLM 业务）、`agents/{designer,producer,writer}.py`（各单一 LLM 能力，过 schema）、`authoring_schemas.py`、`cli.py`；CLI 子命令对标 `--mode` 可独立重入：`generate <brief>`（全量）、`regenerate --node/--agent/--file`（局部）、`validate <id>`、`review <id>`（人审 dump）、`assets <id>`（Artist）；每阶段产物落盘、可断点续跑。

---

## E. 全局回退/灰度（横切，单列）

### E-1 [blocker] 整条流水线只有"apply_routing↔v2 一行开关"一种回退，缺不可逆步骤的回退预案与分故事灰度

- **现状**：§8 回退策略只写两条可逆开关（apply_routing↔v2、resolve_ending_id↔resolve_ending）。全文 grep 灰度/canary/分故事开关 = 0。但多步是不可逆或全局生效：阶段零删 hbm_scenario.yaml 双真值源后无开关回退；阶段四前端"彻底去静态常量、全部从 ui_text 注入"是全前端一次性切换，无 per-story fallback（风险表提"前端保留旧常量作 fallback"与"彻底去常量"矛盾，未对账）；ui_text 下发是全局改 routes.py，没有"新故事走下发、HBM 仍走静态"的灰度位。
- **为什么是缺口**：用户明确要审"回退/灰度"。当前是"要么全切要么全不切"——前端去常量上线后任一 ui_text 字段缺失就全前端白屏，无法只对问题故事回退；seed 改写出错时因已删旧 scenario 块而无路可退。缺"按 story_id 灰度"和"不可逆步骤的影子运行期"，每个里程碑都是大爆炸式切换。
- **补到哪**：dev_logs/42 §8 上方新增"回退粒度与灰度策略"；§6 每阶段标注"是否可逆 + 回退手段 + 是否支持 per-story 灰度"。
- **具体补什么**：(1) 定义按 story_id 的链路灰度位 `use_story_pack(story_id)`：HBM 暂走旧 scenario、新故事走 Story Pack，两条 seed/路由/前端链路并存到充分验证；(2) 不可逆步骤（删 scenario 块、删旧 apply_routing）前强制"影子期"：新旧并行播种/路由、逐帧比对入 trace，零差异维持 ≥1 里程碑后才删旧；(3) 前端去常量改为"ui_text 缺字段→回退内置默认常量并告警"而非白屏，与风险表 fallback 对齐；(4) 每阶段 PR 必须写明回退命令（开关名/还原 commit）。
- **不补的后果**：换故事/迁移的每个里程碑都是高风险一次性切换，一个字段缺失即全前端白屏，且不可逆步骤出错无路可退。

---

## 附：补充后，方案对齐了用户提过的哪些需求（对照勾选表）

| 用户需求 | 是否对齐 | 由哪些补充支撑（关键项） |
|---|---|---|
| **只改 config 换世界**（不改源码） | ✅ 补充后对齐 | A-1~A-9（routing 表驱动全覆盖）、B-1/B-3（relation/移动配置化）、C-2/C-3（参考包+通用 gate）、C-6（缺字段策略） |
| **phase → DAG**（幕制升级为节点图） | ✅ 对齐 | A-1/A-2/A-8（trigger/窗口/不变量进 schema）、A-3（early_end 升格）、C-10（node/edge 级 trace） |
| **涌现社交保留**（关系自发演化不被压死） | ⚠️ 部分对齐 | B-1（relation_types 灌入）、B-2（on_change 确定性兜底）落地后才算真保留；当前 on_change 空转是 blocker |
| **硬骨架 + 自由演员** | ⚠️ 部分对齐 | A-6（agent_behaviors when 字段级 schema）、B-3（自由移动旋钮）、B-7（control_profile 聚合）——A-6/B-3 落地前"自由演员"仍写死代码 |
| **用户只写剧情 → agent 生成** | ⚠️ 重大缺口待补 | D-1（brief 契约）、D-2（agent schema）、D-3（回路）、D-4（Artist）四个 blocker 全补齐才成立；当前流水线实现度≈0 |
| **世界实时变化**（非 turn 驱动持续运行） | ⚠️ 部分对齐 | B-5（常驻循环配置）、B-6（tick/turn 时序契约）、A-9（ending→pause loop）；B-6 未定则世界自走期间推进/结局会漏判 |
| **关系 & 记忆实时** | ⚠️ 部分对齐 | B-1（关系类型生效）、B-2（关系迁移确定性兜底）；记忆侧仅 C-13 存档/恢复涉及，实时写入本身已有实现但无版本化快照 |
| **用户微调**（生成后人审修正） | ❌ 待补 | D-5（人审入口）、D-6（局部重生）、D-9（CLI 命令面）——当前零设计，仅"手改裸 YAML" |
| **可观测性 / 可回归 / 等价迁移** | ⚠️ 待补 | C-10（路由/裁判 trace）、C-11（逐帧 harness）、C-2/C-3（参考包+通用 gate）；harness 不建则"逐帧等价"硬门槛无法执行 |
| **成本 / 性能可控** | ⚠️ 待补 | 运行期已算（§43 §3.1）；生成期 D-8 完全空白，需补预算+配额 |
| **安全（生成不碰玩家存档）/ 回退灰度** | ❌ 待补 | C-4（机制级隔离，当前仅文档红线）、E-1（分故事灰度+影子期，当前仅一行开关）——两者均 blocker |

**图例**：✅ 补充全部落地后该需求成立；⚠️ 列出的补充项中含 blocker/important，未补前该需求只是口号；❌ 当前实现度≈0，必须补齐对应 blocker 才有最小可用形态。

---

## 严重度汇总（便于排期）

- **blocker（不补则换故事/迁移直接失败）**：A-1、A-2、A-3、A-4、B-1、B-2、B-3、C-1、C-2、C-3、C-4、C-9（按后果上修）、D-1、D-2、D-3、D-4、E-1 —— 共 17 项。
- **important**：A-5、A-6、A-7、A-8、A-9、B-4、B-5、B-6、C-5、C-6、C-7、C-8、C-10、C-11、C-12、D-5、D-6、D-7、D-8、D-9 —— 共 20 项。
- **nice-to-have**：A-10、B-7、C-13、C-14 —— 共 4 项。

> 诚实说明：原清单 41 条经去重合并为 41→约 36 个独立条目（A-6 合并 2 条同义、D-2 合并 2 条同义、A-2 吸收 A-7 时间窗写入侧的部分动作）。其中"用户只写剧情→agent 生成→微调"整条设计期流水线（D 类）和"生成不碰存档/回退灰度"（C-4、E-1）是当前实现度最低、风险最集中的区域——这些不是优化项，是"换一个完全不同的故事"能否真正成立的前置条件。
