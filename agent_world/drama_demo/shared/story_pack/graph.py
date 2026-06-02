"""StoryGraph：【已退役·空壳】story_graph（分幕/节点 DAG）已被 berts.yaml（条件→反应链）取代。

全仓已无 story_graph.yaml，loader 永远走 `StoryGraph.empty()`。保留这个极小空壳仅供 loader/pack
安全降级（`pack.validate()` 调 `graph.validate()` → []）；已不含任何节点模型(StoryNode/Edge/Ending)
与图算法(拓扑/可达/路径枚举/V1–V6)——那些随 story_graph 退役一并删除（见 dev_logs/48）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StoryGraph:
    """已退役的故事图空壳：剧情结构改由 berts.yaml 承载，本类不再含节点/边/结局与图算法。"""

    initial_node: str = ""
    nodes: Dict[str, Any] = field(default_factory=dict)
    endings: Dict[str, Any] = field(default_factory=dict)
    edges: List[Any] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "StoryGraph":
        return cls()

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "StoryGraph":
        # story_graph 已退役：无论文件内容如何都返回空壳（剧情由 berts.yaml 驱动）。
        return cls()

    def validate(self) -> List[str]:
        return []  # 空壳恒结构合法；剧情结构/反应链可达性由 BertSet.validate 兜
