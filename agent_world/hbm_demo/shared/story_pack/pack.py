"""StoryPack：整包聚合加载 + 跨文件引用闭合校验（dev_logs/46 C 类缺口）。

把 meta / story_graph / places / agents / relations / relation_types / groups / signals
聚合成一个 StoryPack，并做**跨文件引用闭合**校验（X 系列不变量）：故事图里引用的
agent/place/关键词集合/信号/参数，必须在对应数据文件里真实存在，否则换故事时运行期会
静默错配（注入错 agent、移动到不存在的地点、trigger 引用空关键词集合……）。

纯数据层（D3：不依赖 features）。trigger/actions 仍不透明，但本层按**字段名**做引用闭合，
与具体 trigger 类型解耦（前向兼容新增 trigger 类型）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Set

from agent_world.hbm_demo.shared.prompt_paths import story_dir
from agent_world.hbm_demo.shared.story_pack.errors import StoryPackValidationError
from agent_world.hbm_demo.shared.story_pack.graph import StoryGraph
from agent_world.hbm_demo.shared.story_pack.loader import _load_yaml, load_meta


# 可选文件：缺失时以空内容降级（引擎走默认），不报错。
_OPTIONAL = ("places", "agents", "relations", "relation_types", "groups", "signals")


@dataclass
class StoryPack:
    story_id: str
    meta: Dict[str, Any]
    graph: StoryGraph
    places: Dict[str, Any] = field(default_factory=dict)
    agents: Dict[str, Any] = field(default_factory=dict)
    relations: Dict[str, Any] = field(default_factory=dict)
    relation_types: Dict[str, Any] = field(default_factory=dict)
    groups: Dict[str, Any] = field(default_factory=dict)
    signals: Dict[str, Any] = field(default_factory=dict)

    # ---------- 引用集合（供闭合校验/解释器复用）----------
    def agent_ids(self) -> Set[int]:
        return {int(a["agent_id"]) for a in self.agents.get("agents", []) if "agent_id" in a}

    def place_ids(self) -> Set[str]:
        return {str(p["place_id"]) for p in self.places.get("places", []) if "place_id" in p}

    def relation_type_names(self) -> Set[str]:
        return {str(t["type"]) for t in self.relation_types.get("relation_types", []) if "type" in t}

    def keyword_set_names(self) -> Set[str]:
        return set((self.signals.get("keyword_sets") or {}).keys())

    def story_advance_signals(self) -> Set[str]:
        return set((self.signals.get("story_advance") or {}).get("valid_signals") or [])

    def param_names(self) -> Set[str]:
        return set((self.signals.get("params") or {}).keys())

    def group_ids(self) -> Set[int]:
        return {int(g["group_id"]) for g in self.groups.get("groups", []) if "group_id" in g}

    def behavior_hint_labels(self) -> Set[str]:
        labels: Set[str] = set()
        for _pid, spec in (self.places.get("place_behaviors") or {}).items():
            for mut in (spec or {}).get("mutations", []) or []:
                if "label" in mut:
                    labels.add(str(mut["label"]))
        return labels

    # ---------- validate ----------
    def validate(self) -> List[str]:
        """图结构(V) + 跨文件引用闭合(X) 的全部违例。"""
        issues: List[str] = list(self.graph.validate())
        issues.extend(self._validate_cross_refs())
        return issues

    def validate_or_raise(self) -> None:
        issues = self.validate()
        if issues:
            raise StoryPackValidationError(issues)

    def _validate_cross_refs(self) -> List[str]:
        out: List[str] = []
        agent_ids = self.agent_ids()
        place_ids = self.place_ids()
        kw_names = self.keyword_set_names()
        sa_signals = self.story_advance_signals()
        param_names = self.param_names()
        rel_types = self.relation_type_names()
        edge_ids = {e.id for e in self.graph.edges}
        hint_labels = self.behavior_hint_labels()

        # 若 agents/places 缺失（可选文件未提供），跳过依赖它们的闭合（降级）。
        have_agents = bool(agent_ids)
        have_places = bool(place_ids)

        def chk_agent(aid: Any, ctx: str) -> None:
            if not have_agents:
                return
            for one in aid if isinstance(aid, list) else [aid]:
                try:
                    if int(one) not in agent_ids:
                        out.append(f"[X1] {ctx} 引用了不存在的 agent_id：{one}")
                except (TypeError, ValueError):
                    out.append(f"[X1] {ctx} 的 agent_id 非整数：{one!r}")

        def chk_place(pid: Any, ctx: str) -> None:
            if have_places and str(pid) not in place_ids:
                out.append(f"[X2] {ctx} 引用了不存在的 place_id：{pid}")

        # story_graph：inject_agents / place_focus
        for nid, node in self.graph.nodes.items():
            chk_agent(node.inject_agents, f"node '{nid}'.inject_agents")
            if node.place_focus:
                chk_place(node.place_focus, f"node '{nid}'.place_focus")

        # story_graph：edge actions + trigger 叶子（按字段名闭合）
        for e in self.graph.edges:
            for act in e.actions:
                a_type = act.get("type")
                if a_type == "move_agent":
                    chk_agent(act.get("agent"), f"edge '{e.id}' move_agent")
                    chk_place(act.get("to"), f"edge '{e.id}' move_agent.to")
                elif a_type == "place_mutation":
                    chk_place(act.get("place"), f"edge '{e.id}' place_mutation.place")
                    ref = act.get("behavior_hint_ref")
                    if ref and hint_labels and str(ref) not in hint_labels:
                        out.append(
                            f"[X3] edge '{e.id}' place_mutation 引用了未定义的 behavior_hint_ref：{ref}"
                        )
            for leaf in _walk_trigger(e.trigger):
                if "keyword_set" in leaf and kw_names and str(leaf["keyword_set"]) not in kw_names:
                    out.append(
                        f"[X4] edge '{e.id}' trigger 引用了不存在的 keyword_set：{leaf['keyword_set']}"
                    )
                if "signal" in leaf and sa_signals and str(leaf["signal"]) not in sa_signals:
                    out.append(
                        f"[X4] edge '{e.id}' trigger 引用了未声明的 story_advance 信号：{leaf['signal']}"
                    )
                if "gte_ref" in leaf and param_names and str(leaf["gte_ref"]) not in param_names:
                    out.append(
                        f"[X4] edge '{e.id}' trigger 引用了不存在的参数：{leaf['gte_ref']}"
                    )
                if "unless_edge" in leaf and str(leaf["unless_edge"]) not in edge_ids:
                    out.append(
                        f"[X4] edge '{e.id}' trigger 的 unless_edge 不是已知 edge：{leaf['unless_edge']}"
                    )
                for fld in ("sender", "recipient"):
                    if fld in leaf:
                        chk_agent(leaf[fld], f"edge '{e.id}' trigger.{fld}")
                if "place" in leaf:
                    chk_place(leaf["place"], f"edge '{e.id}' trigger.place")

        # relations：src/dst ∈ agents；type ∈ relation_types
        for r in self.relations.get("relations", []) or []:
            chk_agent(r.get("src"), "relations.src")
            chk_agent(r.get("dst"), "relations.dst")
            rtype = r.get("type")
            if rtype and rel_types and str(rtype) not in rel_types:
                out.append(f"[X5] relations 引用了未在 relation_types 声明的类型：{rtype}")

        # coverage：src/dst ∈ places
        for c in self.places.get("coverage", []) or []:
            chk_place(c.get("src"), "coverage.src")
            chk_place(c.get("dst"), "coverage.dst")

        # groups：members/creator ∈ agents
        for g in self.groups.get("groups", []) or []:
            chk_agent(g.get("members", []), f"group {g.get('group_id')}.members")
            if "creator_id" in g:
                chk_agent(g.get("creator_id"), f"group {g.get('group_id')}.creator_id")

        # meta.player：start_place ∈ places，agent_id ∈ agents
        player = (self.meta.get("player") or {})
        if "start_place" in player:
            chk_place(player.get("start_place"), "meta.player.start_place")
        if "agent_id" in player:
            chk_agent(player.get("agent_id"), "meta.player.agent_id")

        return out


def _walk_trigger(node: Any) -> Iterator[Dict[str, Any]]:
    """递归遍历 trigger 树，产出叶子条件 dict（跳过 any_of/all_of 组合子）。"""
    if not isinstance(node, dict):
        return
    if "any_of" in node:
        for sub in node.get("any_of") or []:
            yield from _walk_trigger(sub)
    elif "all_of" in node:
        for sub in node.get("all_of") or []:
            yield from _walk_trigger(sub)
    else:
        yield node


def load_story_pack(story_id: str) -> StoryPack:
    """加载整包（meta + story_graph + 可选世界原语文件）。不自动 validate。"""
    from agent_world.hbm_demo.shared.story_pack.loader import load_story_graph

    meta = load_meta(story_id)
    graph = load_story_graph(story_id)
    pack = StoryPack(story_id=story_id, meta=meta, graph=graph)
    base = story_dir(story_id)
    for name in _OPTIONAL:
        path = base / f"{name}.yaml"
        if path.is_file():
            setattr(pack, name, _load_yaml(path))
    return pack


def load_and_validate_story_pack(story_id: str) -> StoryPack:
    pack = load_story_pack(story_id)
    pack.validate_or_raise()
    return pack
