# shared/story_pack — Story Pack 数据层

把剧情从代码里抽出来后的**数据承载层**：故事图（DAG）的纯数据结构 + 图算法 + validate 闸门 + 加载器。
**无业务规则、不依赖 `features/`**（遵守 D3）。故事的"解释"（信号→转移）在 L2 `features/f05_story_routing`，
运行期"播种"在 L1。设计见 dev_logs/42 §3·§4、dev_logs/45 §4。

## 文件职责表

| 文件 | 职责 |
|------|------|
| `__init__.py` | 公共出口：StoryGraph/StoryNode/StoryEnding/StoryEdge、load_*、错误类型 |
| `model.py` | 节点/结局/边三类 dataclass + `from_mapping` 解析；trigger/actions 保持不透明 |
| `graph.py` | `StoryGraph` 容器 + 图算法（拓扑排序/可达性/路径枚举）+ `validate()` 闸门（不变量 V1–V6）|
| `errors.py` | `StoryPackError` / `StoryPackValidationError`（聚合违例列表）|
| `loader.py` | 从 `config/stories/<id>/` 读 meta.yaml + story_graph.yaml；`load_and_validate_*` 加载即校验 |

## validate 不变量（V1–V6，详见 graph.py docstring）

V1 initial_node 存在 · V2 id 唯一且 node/ending 不相交 · V3 边端点引用闭合 + 结局终结 ·
V4 节点子图无环 · V5 无孤儿节点 · V6 结局均可达且至少一个可达。

> 本目录是 G0 第一竖切，当前只承载 story_graph + meta。后续切片再补 places/agents/relations/
> relation_types 等文件的加载与**跨文件引用闭合**校验（dev_logs/46 A/B/C 类缺口）。
