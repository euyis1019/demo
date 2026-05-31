"""Story Pack 故事图的纯数据结构（dev_logs/42 §3 / dev_logs/45）。

节点 / 结局 / 边三类 dataclass。trigger 与 actions 在本层**保持不透明**
（原样存 dict）——解释器（L2 features/f05）才消费它们；数据层只负责承载与结构校验。
每个 dataclass 保留 ``raw`` 原始 mapping，做前向兼容（schema 演进新增字段不丢）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from agent_world.hbm_demo.shared.story_pack.errors import StoryPackError


def _require(mapping: Dict[str, Any], key: str, ctx: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise StoryPackError(f"{ctx} 缺少必填字段 '{key}'：{mapping!r}")
    return mapping[key]


@dataclass(frozen=True)
class StoryNode:
    """一个剧情节点（旧 Phase 的数据化身）。

    beats_label 是只读展示标签（如 "Phase 1"），不再承担控制流。
    inject_agents：玩家这一拍的话注入给哪些 agent（替代 routing.PHASE_INJECT_AGENTS）。
    """

    id: str
    beats_label: str = ""
    summary: str = ""
    place_focus: str = ""
    inject_agents: List[int] = field(default_factory=list)
    window_since: str = "start_tick"  # 检测离开本节点的转移时，时间窗起点用的 session 字段
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "StoryNode":
        nid = str(_require(data, "id", "node"))
        agents_raw = data.get("inject_agents") or []
        inject_agents = [int(a) for a in agents_raw]
        return cls(
            id=nid,
            beats_label=str(data.get("beats_label", "")),
            summary=str(data.get("summary", "")),
            place_focus=str(data.get("place_focus", "")),
            inject_agents=inject_agents,
            window_since=str(data.get("window_since", "start_tick")),
            raw=dict(data),
        )


@dataclass(frozen=True)
class StoryEnding:
    """一个终局节点（终结，无出边）。"""

    id: str
    kind: str = "neutral"  # good | neutral | bad
    summary: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "StoryEnding":
        eid = str(_require(data, "id", "ending"))
        return cls(
            id=eid,
            kind=str(data.get("kind", "neutral")),
            summary=str(data.get("summary", "")),
            raw=dict(data),
        )


@dataclass(frozen=True)
class StoryEdge:
    """一条转移边：src 节点 →（trigger 满足时执行 actions，转移到）→ dst。

    trigger / actions 对数据层不透明，解释器消费：
      - trigger: 命中条件（RDC 链 / 关键词 / story_advance 信号 / 超时 / 决策表…）
      - actions: 命中后的副作用（移动 agent / 地点变异 / 换节点…）
    """

    id: str
    src: str
    dst: str
    trigger: Dict[str, Any] = field(default_factory=dict)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "StoryEdge":
        eid = str(_require(data, "id", "edge"))
        src = str(_require(data, "from", "edge"))
        dst = str(_require(data, "to", "edge"))
        trigger = data.get("trigger") or {}
        actions = data.get("actions") or []
        if not isinstance(trigger, dict):
            raise StoryPackError(f"edge '{eid}' 的 trigger 必须是 mapping")
        if not isinstance(actions, list):
            raise StoryPackError(f"edge '{eid}' 的 actions 必须是 list")
        return cls(
            id=eid,
            src=src,
            dst=dst,
            trigger=dict(trigger),
            actions=[dict(a) for a in actions],
            raw=dict(data),
        )
