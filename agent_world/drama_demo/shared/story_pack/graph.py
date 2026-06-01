"""StoryGraph：故事 DAG 容器 + 图算法 + validate 闸门（dev_logs/45 §4）。

借鉴 AI4VisualNovel `agents/story_graph.py` 的硬校验，但产出我们自己的 schema。
节点（StoryNode）之间靠 StoryEdge 连接，边的终点可以是另一个节点或一个结局
（StoryEnding，终结、无出边）。validate() 把全部结构不变量违例聚合返回。

不变量（与 dev_logs/45 §4.2 对齐）：
  V1  initial_node 必填且存在于 nodes
  V2  node/ending/edge id 各自唯一；node 与 ending 的 id 集合不相交
  V3  每条边 src 必须是节点；dst 必须是节点或结局（结局不可作为 src → 终结性）
  V4  节点之间无环（节点子图是 DAG）
  V5  每个节点都可从 initial_node 抵达（无孤儿节点）
  V6  每个结局都可从 initial_node 抵达；且至少存在一个可达结局
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from agent_world.drama_demo.shared.story_pack.errors import (
    StoryPackError,
    StoryPackValidationError,
)
from agent_world.drama_demo.shared.story_pack.model import (
    StoryEdge,
    StoryEnding,
    StoryNode,
)

# 当前解释器支持的 story_graph schema 版本（dev_logs/46 C-5：演进需可检测）。
SUPPORTED_SCHEMA_VERSIONS = (1,)


@dataclass
class StoryGraph:
    """故事图：节点 + 结局 + 边 + 起点。"""

    initial_node: str
    nodes: Dict[str, StoryNode] = field(default_factory=dict)
    endings: Dict[str, StoryEnding] = field(default_factory=dict)
    edges: List[StoryEdge] = field(default_factory=list)
    schema_version: int = 1

    # ---------- 构造 ----------
    @classmethod
    def empty(cls) -> "StoryGraph":
        """空图：bert（条件→反应）驱动的包没有 story_graph.yaml，剧情结构改由 berts.yaml 承载。"""
        return cls(initial_node="")

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "StoryGraph":
        if not isinstance(data, dict):
            raise StoryPackError("story_graph 顶层必须是 mapping")
        initial = data.get("initial_node")
        # 空图（bert 驱动包，无 story_graph.yaml / 空文件）合法降级：剧情由 berts.yaml 驱动。
        if not initial and not (data.get("nodes") or data.get("endings") or data.get("edges")):
            return cls.empty()
        if not initial:
            raise StoryPackError("story_graph 缺少 initial_node")

        nodes: Dict[str, StoryNode] = {}
        for raw in data.get("nodes") or []:
            node = StoryNode.from_mapping(raw)
            if node.id in nodes:
                raise StoryPackError(f"重复节点 id：{node.id}")
            nodes[node.id] = node

        endings: Dict[str, StoryEnding] = {}
        for raw in data.get("endings") or []:
            ending = StoryEnding.from_mapping(raw)
            if ending.id in endings:
                raise StoryPackError(f"重复结局 id：{ending.id}")
            endings[ending.id] = ending

        edges = [StoryEdge.from_mapping(raw) for raw in (data.get("edges") or [])]

        return cls(
            initial_node=str(initial),
            nodes=nodes,
            endings=endings,
            edges=edges,
            schema_version=int(data.get("schema_version", 1)),
        )

    # ---------- 查询 ----------
    def is_node(self, ident: str) -> bool:
        return ident in self.nodes

    def is_ending(self, ident: str) -> bool:
        return ident in self.endings

    def get_children(self, node_id: str) -> List[Tuple[StoryEdge, str]]:
        """返回 (边, 终点 id) 列表——从 node_id 出发的所有边。"""
        return [(e, e.dst) for e in self.edges if e.src == node_id]

    # ---------- 图算法 ----------
    def topological_sort(self) -> List[str]:
        """对节点子图（仅 node→node 边）做拓扑排序（Kahn）。有环则抛错。"""
        node_ids = list(self.nodes.keys())
        indeg = {nid: 0 for nid in node_ids}
        adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        for e in self.edges:
            if e.src in self.nodes and e.dst in self.nodes:
                adj[e.src].append(e.dst)
                indeg[e.dst] += 1
        queue = [nid for nid in node_ids if indeg[nid] == 0]
        order: List[str] = []
        while queue:
            cur = queue.pop(0)
            order.append(cur)
            for nxt in adj[cur]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(node_ids):
            remaining = sorted(set(node_ids) - set(order))
            raise StoryPackError(f"节点子图存在环，涉及：{remaining}")
        return order

    def reachable_from_initial(self) -> set[str]:
        """从 initial_node 经任意边可达的全部 id（含节点与结局）。"""
        seen: set[str] = set()
        if self.initial_node not in self.nodes:
            return seen
        stack = [self.initial_node]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for _edge, dst in self.get_children(cur):
                if dst not in seen:
                    stack.append(dst)
        return seen

    def get_reachable_endings(self) -> List[str]:
        reach = self.reachable_from_initial()
        return sorted(eid for eid in self.endings if eid in reach)

    def enumerate_all_paths(self, max_paths: int = 1000) -> List[List[str]]:
        """枚举 initial_node → 各结局的全部路径（id 序列）。

        节点子图是 DAG（validate 保证），故路径有限。``max_paths`` 是防爆护栏。
        """
        paths: List[List[str]] = []

        def dfs(cur: str, trail: List[str]) -> None:
            if len(paths) >= max_paths:
                return
            if cur in self.endings:
                paths.append(list(trail))
                return
            children = self.get_children(cur)
            if not children:
                paths.append(list(trail))  # 死路（非结局的叶子）——validate 会另行报
                return
            for _edge, dst in children:
                dfs(dst, trail + [dst])

        if self.initial_node in self.nodes:
            dfs(self.initial_node, [self.initial_node])
        return paths

    # ---------- validate 闸门 ----------
    def validate(self) -> List[str]:
        """返回违例列表（空 = 通过）。每条以 [V?] 不变量编号开头。"""
        # 空图（bert 驱动包，无分幕/节点）结构性合法——剧情结构与可达性由 BertSet.validate 兜。
        if not self.nodes and not self.endings and not self.edges:
            return []
        issues: List[str] = []
        node_ids = set(self.nodes)
        ending_ids = set(self.endings)

        # V0 schema 版本兼容性
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            issues.append(
                f"[V0] 不支持的 schema_version={self.schema_version}（当前支持 {SUPPORTED_SCHEMA_VERSIONS}）"
            )

        # V1 initial_node
        if self.initial_node not in node_ids:
            issues.append(f"[V1] initial_node '{self.initial_node}' 不在 nodes 中")

        # V2 id 唯一性 + 不相交（重复在 from_mapping 已拦；此处查交集）
        overlap = node_ids & ending_ids
        if overlap:
            issues.append(f"[V2] node 与 ending id 重叠：{sorted(overlap)}")
        seen_edge: set[str] = set()
        for e in self.edges:
            if e.id in seen_edge:
                issues.append(f"[V2] 重复 edge id：{e.id}")
            seen_edge.add(e.id)

        # V3 边端点引用闭合 + 结局终结性
        valid_targets = node_ids | ending_ids
        for e in self.edges:
            if e.src not in node_ids:
                if e.src in ending_ids:
                    issues.append(f"[V3] edge '{e.id}' 以结局 '{e.src}' 为起点（结局须终结）")
                else:
                    issues.append(f"[V3] edge '{e.id}' 的 from '{e.src}' 不是已知节点")
            if e.dst not in valid_targets:
                issues.append(f"[V3] edge '{e.id}' 的 to '{e.dst}' 不是已知节点或结局")

        # V4 无环（仅在端点引用基本闭合时才有意义）
        if not any(it.startswith("[V3]") for it in issues):
            try:
                self.topological_sort()
            except StoryPackError as exc:
                issues.append(f"[V4] {exc}")

        # V5 / V6 可达性
        reach = self.reachable_from_initial()
        orphan_nodes = sorted(node_ids - reach)
        if orphan_nodes:
            issues.append(f"[V5] 存在从 initial_node 不可达的孤儿节点：{orphan_nodes}")
        unreachable_endings = sorted(ending_ids - reach)
        if unreachable_endings:
            issues.append(f"[V6] 存在不可达结局：{unreachable_endings}")
        if ending_ids and not (ending_ids & reach):
            issues.append("[V6] 没有任何结局可从 initial_node 抵达")

        return issues

    def validate_or_raise(self) -> None:
        issues = self.validate()
        if issues:
            raise StoryPackValidationError(issues)
