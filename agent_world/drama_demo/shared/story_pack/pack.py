"""StoryPack：整包聚合加载 + 跨文件引用闭合校验（dev_logs/46 C 类缺口）。

把 meta / story_graph / places / agents / relations / relation_types / groups / signals
聚合成一个 StoryPack，并做**跨文件引用闭合**校验（X 系列不变量）：relations/coverage/groups/
meta.player 引用的 agent/place/relation_type，必须在对应数据文件里真实存在，否则换故事时
运行期会静默错配（注入错 agent、移动到不存在的地点……）。

剧情结构已改由 berts.yaml（条件→反应链）承载，story_graph 退役；节点图/trigger 相关的
跨文件闭合段已随之删除（运行期恒空，无效力），本层只保留对 bert 包仍有效的世界原语闭合。

纯数据层（D3：不依赖 features）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from agent_world.drama_demo.shared.prompt_paths import story_dir
from agent_world.drama_demo.shared.story_pack.bert import BertSet
from agent_world.drama_demo.shared.story_pack.errors import StoryPackValidationError
from agent_world.drama_demo.shared.story_pack.graph import StoryGraph
from agent_world.drama_demo.shared.story_pack.loader import _load_yaml, load_meta


# 可选文件：缺失时以空内容降级（引擎走默认），不报错。
_OPTIONAL = ("places", "agents", "relations", "relation_types", "groups", "signals")


@dataclass
class StoryPack:
    story_id: str
    meta: Dict[str, Any]
    graph: StoryGraph
    berts: BertSet = field(default_factory=BertSet)  # 「条件→反应」规则集（取代任务链；旧包为空）
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

    def group_ids(self) -> Set[int]:
        return {int(g["group_id"]) for g in self.groups.get("groups", []) if "group_id" in g}

    # ---------- validate ----------
    def validate(self, *, strict: bool = False) -> List[str]:
        """图结构(V) + 跨文件引用闭合(X) + bert 规则集(B) 的全部违例（结构性，供播种/骨架编译共用）。

        strict=True 时额外加 bert「开局可玩面」软门禁（[B9]/[B10]）——仅生成期用，逼管理 agent 产出
        玩家上手即可推进的开局；运行期加载默认 strict=False，不因可玩面问题拒载已有故事。
        """
        issues: List[str] = list(self.graph.validate())
        issues.extend(self._validate_cross_refs())
        if self.berts.berts:  # 仅当本包采用 bert 时才校验（旧任务包 berts 为空，跳过）
            # agents/places 可选文件缺失时传 None，沿用「降级跳过该闭合」约定。
            issues.extend(self.berts.validate(
                agent_ids=(self.agent_ids() or None),
                place_ids=(self.place_ids() or None),
                strict=strict,
            ))
        return issues

    def validate_or_raise(self) -> None:
        issues = self.validate()
        if issues:
            raise StoryPackValidationError(issues)

    def _validate_cross_refs(self) -> List[str]:
        out: List[str] = []
        agent_ids = self.agent_ids()
        place_ids = self.place_ids()
        rel_types = self.relation_type_names()

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

        # agents[].location ∈ places —— 引擎 set_location 有 place 外键，location 不是已定义 place 会在播种期
        # FK 崩溃（前端表现为「Runner 启动即退出」）。生成期 LLM 偶尔给出近似但对不上的地名（如「大堂窗边」vs
        # 「窗边」），validate 原先不查这条，于是漏到运行期才崩。这里提前闭合：每个 agent 必须有 location 且 ∈ places。
        if have_places:
            for a in self.agents.get("agents", []) or []:
                loc = a.get("location")
                ctx = f"agent {a.get('agent_id')}({a.get('name', '')}).location"
                if loc in (None, ""):
                    out.append(f"[X2] {ctx} 缺失（每个 agent 必须有出生 place）")
                else:
                    chk_place(loc, ctx)

        return out


def load_story_pack(story_id: str) -> StoryPack:
    """加载整包（meta + story_graph + berts + 可选世界原语文件）。不自动 validate。"""
    from agent_world.drama_demo.shared.story_pack.loader import load_berts, load_story_graph

    meta = load_meta(story_id)
    graph = load_story_graph(story_id)
    pack = StoryPack(story_id=story_id, meta=meta, graph=graph, berts=load_berts(story_id))
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
