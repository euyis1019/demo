# shared/story_pack — Story Pack 数据层

把剧情从代码里抽出来后的**数据承载层**：故事图（DAG）的纯数据结构 + 图算法 + validate 闸门 + 加载器。
**无业务规则、不依赖 `features/`**（遵守 D3）。故事的"解释"（信号→转移）在 L2 `features/f05_story_routing`，
运行期"播种"在 L1。设计见 dev_logs/42 §3·§4、dev_logs/45 §4。

## 文件职责表

| 文件 | 职责 |
|------|------|
| `__init__.py` | 公共出口：StoryGraph/StoryNode/StoryEnding/StoryEdge、load_*、错误类型 |
| `model.py` | 节点/结局/边三类 dataclass + `from_mapping` 解析；trigger/actions 保持不透明（旧分幕结构，运行期已退居兼容）|
| `bert.py` | **bert（条件→反应）** `Bert`/`BertSet`：`trigger→target→reaction` + `requires/arms` 反应链 + `ending` 结局 bert；`armed_ids(fired)` 算上膛集合、`validate()` 闸门（B 系列）。取代分幕/任务链，是剧情运行期主驱动（见 dev_logs/48）|
| `graph.py` | `StoryGraph` 容器 + 图算法（拓扑排序/可达性/路径枚举）+ `validate()` 闸门（不变量 V1–V6）|
| `errors.py` | `StoryPackError` / `StoryPackValidationError`（聚合违例列表）|
| `loader.py` | 从 `config/stories/<id>/` 读 meta.yaml + story_graph.yaml + **berts.yaml**(`load_berts`)；`load_and_validate_*` 加载即校验 |
| `pack.py` | `StoryPack` 整包聚合（meta+graph+**berts**+世界原语文件）+ **跨文件引用闭合校验**（X 系列）+ bert 校验（B 系列）+ `load_story_pack` |
| `scenario_adapter.py` | `StoryPack` → 运行期 scenario dict 投影（`seed_world`/`build_kernel` 消费）+ 播种开关 `is_story_pack_seed_enabled()` |

## validate 不变量（V1–V6，详见 graph.py docstring）

V1 initial_node 存在 · V2 id 唯一且 node/ending 不相交 · V3 边端点引用闭合 + 结局终结 ·
V4 节点子图无环 · V5 无孤儿节点 · V6 结局均可达且至少一个可达。

## 跨文件引用闭合（X 系列，pack.py，dev_logs/46 C 类）

X1 inject_agents/trigger sender·recipient/relations/groups/player ⊆ agents ·
X2 place_focus/move_agent.to/coverage/player.start_place ⊆ places ·
X3 place_mutation.behavior_hint_ref ∈ place_behaviors 标签 ·
X4 trigger.keyword_set ∈ signals.keyword_sets、signal ∈ story_advance.valid_signals、gte_ref ∈ params、unless_edge ∈ edges ·
X5 relations.type ∈ relation_types。
按**字段名**闭合，与 trigger 具体类型解耦；可选文件缺失时降级跳过对应闭合。

> 仍未承载（后续切片）：timed_events、judges、language_style/ui_text、prompts overlay、
> node.agent_behaviors 行为卡（dev_logs/46 A-6/D 类）。
