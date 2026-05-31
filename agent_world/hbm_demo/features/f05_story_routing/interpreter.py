"""StoryInterpreter：表驱动剧情解释器（dev_logs/42 §4 / dev_logs/45）。

读 Story Pack（story_graph + signals），把节点转移条件（trigger）与副作用（actions）
当**数据**来评估/规划，替代 features/f05_story_routing 里写死的 detect_node_* if 链与
apply_routing 常量。本切片（G0-Slice3）只做**纯决策**：
  - detect_edge：评估某条边的 trigger 是否触发（与 agent_signals 等价）
  - plan_actions：把边的 actions 解析成结构化 effects（移动/地点变异/换 phase），不执行 IPC

真正把 effects 落到运行期（IPC 移动、place_mutation 入队、phase 切换）是 G0-Slice4 的桥接层。
故本模块**不导入也不改动** routing.py，旧路径原样保留，E2E 行为不变。

trigger 叶子类型（数据 → 评估器）：
  story_advance{signal}              → story_signals.has_story_signal（受 story_advance.enabled 门控）
  rdc_pair{sender,recipient}         → 存在任意 RDC（_has_rdc_pair）
  rdc_keyword{sender,recipient,keyword_set} → RDC 命中关键词（recipient 可为列表=OR）
  f2f_keyword{place,sender,keyword_set}     → 该 sender 在该地点的 F2F 命中关键词
  timeout{field,gte_ref,unless_edge} → session 字段 ≥ 参数 且 unless_edge 未触发
node D 的结局判定（phase4_conclusion/turn25_decision）涉及 LLM + stats，列为 deferred，后续切片实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from agent_world.hbm_demo.features.f05_story_routing.story_signals import has_story_signal
from agent_world.hbm_demo.shared.story_pack import StoryPack, load_story_pack
from agent_world.hbm_demo.shared.story_pack.graph import StoryGraph
from agent_world.hbm_demo.shared.story_pack.model import StoryEdge

# node D 结局判定（LLM/stats），本切片暂不评估。
DEFERRED_TRIGGER_TYPES = frozenset(
    {"phase4_conclusion", "turn25_decision", "turn25_decision_default"}
)


@dataclass
class DetectContext:
    db: Any
    since_t: int
    t_now: int
    session: Any


class StoryInterpreter:
    """以一份 Story Pack 驱动剧情决策。"""

    def __init__(self, pack: StoryPack) -> None:
        self.pack = pack
        self.graph: StoryGraph = pack.graph
        signals = pack.signals or {}
        self._keyword_sets: Dict[str, Sequence[str]] = signals.get("keyword_sets") or {}
        self._params: Dict[str, Any] = signals.get("params") or {}
        sa = signals.get("story_advance") or {}
        self._story_advance_enabled: bool = bool(sa.get("enabled", True))

    @classmethod
    def for_story(cls, story_id: str) -> "StoryInterpreter":
        return cls(load_story_pack(story_id))

    # ---------- 数据访问 ----------
    def _keywords(self, name: str) -> tuple[str, ...]:
        return tuple(str(k) for k in (self._keyword_sets.get(name) or ()))

    def _param(self, name: str) -> Any:
        return self._params.get(name)

    def _resolve_since(self, session: Any, source_node_id: str) -> int:
        node = self.graph.nodes.get(source_node_id)
        field = node.window_since if node else "start_tick"
        val = getattr(session, field, None)
        if val is None:
            val = getattr(session, "start_tick", 0)
        return max(0, int(val or 0))

    # ---------- trigger 评估 ----------
    def _eval_leaf(self, leaf: Dict[str, Any], ctx: DetectContext) -> bool:
        ltype = leaf.get("type")

        if ltype == "story_advance":
            if not self._story_advance_enabled:
                return False
            return has_story_signal(
                ctx.db, str(leaf.get("signal", "")), since_t=ctx.since_t, t_now=ctx.t_now
            )

        if ltype == "rdc_pair":
            return self._rdc_exists(
                ctx, sender=leaf.get("sender"), recipient=leaf.get("recipient")
            )

        if ltype == "rdc_keyword":
            keywords = self._keywords(str(leaf.get("keyword_set", "")))
            return self._rdc_keyword(
                ctx, sender=leaf.get("sender"), recipient=leaf.get("recipient"), keywords=keywords
            )

        if ltype == "f2f_keyword":
            keywords = self._keywords(str(leaf.get("keyword_set", "")))
            return self._f2f_keyword(
                ctx, place=str(leaf.get("place", "")), sender=int(leaf.get("sender")), keywords=keywords
            )

        if ltype == "timeout":
            return self._timeout(leaf, ctx)

        if ltype in DEFERRED_TRIGGER_TYPES:
            return False  # node D 结局判定，后续切片实现

        return False  # 未知叶子类型：保守判否（validate 已在加载期把关引用闭合）

    def _eval_trigger(self, trigger: Dict[str, Any], ctx: DetectContext) -> bool:
        if not isinstance(trigger, dict):
            return False
        if "any_of" in trigger:
            return any(self._eval_trigger(sub, ctx) for sub in (trigger.get("any_of") or []))
        if "all_of" in trigger:
            return all(self._eval_trigger(sub, ctx) for sub in (trigger.get("all_of") or []))
        return self._eval_leaf(trigger, ctx)

    # ---------- 叶子原语（与 agent_signals 同源的 db 调用）----------
    @staticmethod
    def _content_matches(content: Any, keywords: Sequence[str]) -> bool:
        text = str(content or "")
        return any(kw in text for kw in keywords)

    def _rdc_exists(self, ctx: DetectContext, *, sender: Any, recipient: Any) -> bool:
        for r in self._recipients(recipient):
            rows = ctx.db.fetch_rdc_messages(
                sender_id=int(sender), recipient_id=int(r), since_t=ctx.since_t, t_now=ctx.t_now
            )
            if len(rows) > 0:
                return True
        return False

    def _rdc_keyword(
        self, ctx: DetectContext, *, sender: Any, recipient: Any, keywords: Sequence[str]
    ) -> bool:
        for r in self._recipients(recipient):
            rows = ctx.db.fetch_rdc_messages(
                sender_id=int(sender), recipient_id=int(r), since_t=ctx.since_t, t_now=ctx.t_now
            )
            for row in rows:
                if self._content_matches(row["content"], keywords):
                    return True
        return False

    def _f2f_keyword(
        self, ctx: DetectContext, *, place: str, sender: int, keywords: Sequence[str]
    ) -> bool:
        fetch = getattr(ctx.db, "fetch_f2f_from_sender_at", None)
        if callable(fetch):
            history = fetch(place, int(sender), int(ctx.t_now), int(ctx.since_t))
        else:
            history = [
                row
                for row in ctx.db.fetch_f2f_history_at(place, int(ctx.t_now), int(ctx.since_t), limit=500)
                if int(row[1]) == int(sender)
            ]
        for _at_t, sender_id, _mid, content in history:
            if int(sender_id) != int(sender):
                continue
            if self._content_matches(content, keywords):
                return True
        return False

    def _timeout(self, leaf: Dict[str, Any], ctx: DetectContext) -> bool:
        field = str(leaf.get("field", "player_turn"))
        limit = self._param(str(leaf.get("gte_ref", "")))
        if limit is None:
            return False
        try:
            value = int(getattr(ctx.session, field, 0) or 0)
        except (TypeError, ValueError):
            return False
        if value < int(limit):
            return False
        unless_edge = leaf.get("unless_edge")
        if unless_edge:
            edge = self._edge_by_id(str(unless_edge))
            if edge is not None and self.detect_edge(edge, ctx.db, ctx.session, ctx.t_now):
                return False
        return True

    @staticmethod
    def _recipients(recipient: Any) -> List[Any]:
        if isinstance(recipient, (list, tuple)):
            return list(recipient)
        return [recipient]

    def _edge_by_id(self, edge_id: str) -> Optional[StoryEdge]:
        for e in self.graph.edges:
            if e.id == edge_id:
                return e
        return None

    # ---------- 对外决策 API ----------
    def detect_edge(self, edge: StoryEdge, db: Any, session: Any, tick: int) -> bool:
        """该边的 trigger 是否触发（since 取源节点 window_since）。"""
        since_t = self._resolve_since(session, edge.src)
        ctx = DetectContext(db=db, since_t=since_t, t_now=int(tick), session=session)
        return self._eval_trigger(edge.trigger, ctx)

    def plan_actions(self, edge: StoryEdge, *, current_tick: int) -> List[Dict[str, Any]]:
        """把边的 actions 解析成结构化 effects（不执行 IPC；Slice4 桥接层消费）。"""
        planned: List[Dict[str, Any]] = []
        for act in edge.actions:
            a_type = act.get("type")
            if a_type == "move_agent":
                planned.append(
                    {"type": "move_agent", "agent": int(act["agent"]), "to": str(act["to"])}
                )
            elif a_type == "place_mutation":
                planned.append(
                    {
                        "type": "place_mutation",
                        "place": str(act["place"]),
                        "behavior_hint": self._resolve_behavior_hint(
                            str(act["place"]), act.get("behavior_hint_ref")
                        ),
                    }
                )
            elif a_type == "set_session":
                value = act.get("value")
                if value == "current_tick":
                    value = int(current_tick)
                planned.append(
                    {"type": "set_session", "field": str(act["field"]), "value": value}
                )
            elif a_type == "advance_player_place":
                planned.append(
                    {"type": "advance_player_place", "new_phase": str(act.get("new_phase", ""))}
                )
            else:
                planned.append(dict(act))  # 透传未知 action（前向兼容）
        return planned

    def _resolve_behavior_hint(self, place: str, ref: Optional[str]) -> str:
        if not ref:
            return ""
        behaviors = (self.pack.places.get("place_behaviors") or {}).get(place) or {}
        for mut in behaviors.get("mutations", []) or []:
            if str(mut.get("label")) == str(ref):
                return str(mut.get("behavior_hint", ""))
        return ""
