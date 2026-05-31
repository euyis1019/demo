#!/usr/bin/env python3
"""StoryInterpreter 离线等价回归（G0-Slice3，dev_logs/45 §6）。

证明：表驱动解释器对 Story Pack 的 detect_edge，与现有写死的 agent_signals.detect_node_*
/ detect_bad_end 在**同一份世界状态**上给出**完全相同**的布尔判定——无需起 Runner/Flask/LLM。

做法：构造一个假 world.db（实现 detect_node_* 与 interpreter 共同调用的 db 方法），喂一组
代表性世界状态，对每个状态断言 interpreter.detect_edge(node_x) == agent_signals.detect_node_x。
两者调用同一假 db，故只要解释器逻辑忠实，结果必然一致；不一致即暴露漂移。

另含一条守卫：signals.yaml 的关键词集合/参数与 routing_config 实际返回值一致（防再次漂移）。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

from agent_world.hbm_demo.features.f05_story_routing import agent_signals as A
from agent_world.hbm_demo.features.f05_story_routing.interpreter import StoryInterpreter

STORY_ID = "hbm_memory_war"


# ---------------- 假 world.db ----------------
class FakeDB:
    """仅实现 detect_node_* 与 interpreter 共同依赖的 db 方法。窗口语义 (since_t, t_now]。"""

    def __init__(self) -> None:
        self.rdc: List[Tuple[int, int, str, int]] = []          # (sender, recipient, content, at_t)
        self.f2f: List[Tuple[str, int, str, int]] = []          # (place, sender, content, at_t)
        self.sigs: List[Tuple[str, int, Optional[int]]] = []    # (signal, at_t, agent_id)

    def add_rdc(self, sender: int, recipient: int, content: str, at_t: int = 5) -> "FakeDB":
        self.rdc.append((sender, recipient, content, at_t))
        return self

    def add_f2f(self, place: str, sender: int, content: str, at_t: int = 5) -> "FakeDB":
        self.f2f.append((place, sender, content, at_t))
        return self

    def add_signal(self, signal: str, at_t: int = 5, agent_id: Optional[int] = None) -> "FakeDB":
        self.sigs.append((signal, at_t, agent_id))
        return self

    # --- db API ---
    def fetch_rdc_messages(self, *, sender_id: int, recipient_id: int, since_t: int, t_now: int) -> List[Dict[str, Any]]:
        return [
            {"content": c}
            for (s, r, c, t) in self.rdc
            if s == sender_id and r == recipient_id and since_t < t <= t_now
        ]

    def fetch_f2f_history_at(self, place_id: str, t_now: int, since_t: int, limit: int = 200) -> List[Tuple[int, int, int, str]]:
        rows = [
            (t, s, 0, c)
            for (p, s, c, t) in self.f2f
            if p == place_id and since_t < t <= t_now
        ]
        rows.sort(key=lambda x: x[0])
        return rows[-limit:]

    def fetch_f2f_from_sender_at(self, place_id: str, sender_id: int, t_now: int, since_t: int) -> List[Tuple[int, int, int, str]]:
        return [r for r in self.fetch_f2f_history_at(place_id, t_now, since_t, limit=10_000) if r[1] == sender_id]

    def fetch_story_advance_since(self, since_t: int, t_now: int, *, signal: str, agent_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return [
            {"signal": sg}
            for (sg, t, aid) in self.sigs
            if sg == signal and since_t < t <= t_now and (agent_id is None or aid == agent_id)
        ]


class FakeSession:
    def __init__(self, phase: str, *, player_turn: int = 1, start_tick: int = 0,
                 phase2_start_tick: Optional[int] = None, phase3_start_tick: Optional[int] = None,
                 phase4_start_tick: Optional[int] = None) -> None:
        self.phase = phase
        self.player_turn = player_turn
        self.start_tick = start_tick
        self.phase2_start_tick = phase2_start_tick
        self.phase3_start_tick = phase3_start_tick
        self.phase4_start_tick = phase4_start_tick


_INTERP = StoryInterpreter.for_story(STORY_ID)
T_NOW = 50


def _assert_equiv(label: str, edge_id: str, legacy: bool, db: FakeDB, session: FakeSession) -> None:
    edge = _INTERP._edge_by_id(edge_id)
    got = _INTERP.detect_edge(edge, db, session, T_NOW)
    assert got == legacy, f"[{label}] interpreter={got} != legacy={legacy}（edge={edge_id}）"


# ---------------- 节点 A 等价矩阵 ----------------
def test_node_a_equivalence() -> None:
    s = FakeSession("Phase 1", start_tick=0)

    # 空状态：都不触发
    _assert_equiv("A空", "node_a", A.detect_node_a(FakeDB(), since_t=0, t_now=T_NOW), FakeDB(), s)

    # 完整 RDC 链 + approve：都触发
    db = (FakeDB().add_rdc(1, 2, "有个天才来了").add_rdc(2, 3, "帮我验证")
          .add_rdc(2, 1, "带进来，私人会议室见"))
    _assert_equiv("A全链", "node_a", A.detect_node_a(db, since_t=0, t_now=T_NOW), db, s)

    # 缺 2→3 求证：都不触发
    db2 = FakeDB().add_rdc(1, 2, "有个天才来了").add_rdc(2, 1, "带进来")
    _assert_equiv("A缺求证", "node_a", A.detect_node_a(db2, since_t=0, t_now=T_NOW), db2, s)

    # RDC 链但无 approve 关键词：都不触发
    db3 = FakeDB().add_rdc(1, 2, "有人").add_rdc(2, 3, "验证").add_rdc(2, 1, "随便")
    _assert_equiv("A无批准词", "node_a", A.detect_node_a(db3, since_t=0, t_now=T_NOW), db3, s)

    # story_advance(approve_visitor)：都触发
    db4 = FakeDB().add_signal("approve_visitor")
    _assert_equiv("A信号", "node_a", A.detect_node_a(db4, since_t=0, t_now=T_NOW), db4, s)


# ---------------- 节点 B 等价矩阵 ----------------
def test_node_b_equivalence() -> None:
    s = FakeSession("Phase 2", phase2_start_tick=10)
    since = 10

    _assert_equiv("B空", "node_b", A.detect_node_b(FakeDB(), since_t=since, t_now=T_NOW), FakeDB(), s)

    # Tech VP 正面 RDC：都触发
    db = FakeDB().add_rdc(3, 2, "理论上成立，简直是核武器", at_t=20)
    _assert_equiv("B正面RDC", "node_b", A.detect_node_b(db, since_t=since, t_now=T_NOW), db, s)

    # Jensen 私人房 F2F 回谈判室：都触发
    db2 = FakeDB().add_f2f("jensen_private_room", 2, "跟我进谈判室", at_t=20)
    _assert_equiv("B返回F2F", "node_b", A.detect_node_b(db2, since_t=since, t_now=T_NOW), db2, s)

    # story_advance(return_to_negotiation)：都触发
    db3 = FakeDB().add_signal("return_to_negotiation", at_t=20)
    _assert_equiv("B信号", "node_b", A.detect_node_b(db3, since_t=since, t_now=T_NOW), db3, s)

    # 窗口外（早于 phase2_start_tick）的 RDC：都不触发
    db4 = FakeDB().add_rdc(3, 2, "核武器", at_t=5)  # at_t < since
    _assert_equiv("B窗口外", "node_b", A.detect_node_b(db4, since_t=since, t_now=T_NOW), db4, s)


# ---------------- 节点 C 等价矩阵 ----------------
def test_node_c_equivalence() -> None:
    s = FakeSession("Phase 3", phase3_start_tick=20)
    since = 20

    _assert_equiv("C空", "node_c", A.detect_node_c(FakeDB(), since_t=since, t_now=T_NOW), FakeDB(), s)

    # Jensen→CEO5 RDC 驱逐：都触发（recipient 列表 OR）
    db = FakeDB().add_rdc(2, 5, "你们出去，谈完了", at_t=30)
    _assert_equiv("C驱逐RDC", "node_c", A.detect_node_c(db, since_t=since, t_now=T_NOW), db, s)

    # Jensen 谈判室 F2F 驱逐：都触发
    db2 = FakeDB().add_f2f("negotiation_room", 2, "请离场", at_t=30)
    _assert_equiv("C驱逐F2F", "node_c", A.detect_node_c(db2, since_t=since, t_now=T_NOW), db2, s)

    # 新增覆盖词「可以走了」(routing.yaml 覆盖项)：都触发——验证 signals 同步
    db3 = FakeDB().add_f2f("negotiation_room", 2, "行了你们可以走了", at_t=30)
    _assert_equiv("C覆盖词", "node_c", A.detect_node_c(db3, since_t=since, t_now=T_NOW), db3, s)

    # story_advance(expel_ceos)：都触发
    db4 = FakeDB().add_signal("expel_ceos", at_t=30)
    _assert_equiv("C信号", "node_c", A.detect_node_c(db4, since_t=since, t_now=T_NOW), db4, s)


# ---------------- 坏结局等价矩阵 ----------------
def test_bad_end_equivalence() -> None:
    # 前台拒绝 F2F：都触发
    s = FakeSession("Phase 1", player_turn=3, start_tick=0)
    db = FakeDB().add_f2f("nvidia_reception", 1, "请离开，保安", at_t=5)
    legacy = A.detect_bad_end(s, db, t_now=T_NOW)
    _assert_equiv("坏拒绝", "bad_end_reject", legacy, db, s)

    # 超时未获批准：都触发（player_turn>=10 且 node_a 不成立）
    s2 = FakeSession("Phase 1", player_turn=10, start_tick=0)
    legacy2 = A.detect_bad_end(s2, FakeDB(), t_now=T_NOW)
    _assert_equiv("坏超时", "bad_end_reject", legacy2, FakeDB(), s2)

    # 超时但 node_a 已成立 → unless_edge 抑制：都不触发
    s3 = FakeSession("Phase 1", player_turn=12, start_tick=0)
    db3 = (FakeDB().add_rdc(1, 2, "天才").add_rdc(2, 3, "验证").add_rdc(2, 1, "批准，这边请"))
    legacy3 = A.detect_bad_end(s3, db3, t_now=T_NOW)
    _assert_equiv("坏超时但放行", "bad_end_reject", legacy3, db3, s3)

    # 早期无事：都不触发
    s4 = FakeSession("Phase 1", player_turn=2, start_tick=0)
    legacy4 = A.detect_bad_end(s4, FakeDB(), t_now=T_NOW)
    _assert_equiv("坏早期", "bad_end_reject", legacy4, FakeDB(), s4)


# ---------------- plan_actions 正确性（对照 routing.apply_routing 副作用）----------------
def test_plan_actions_match_routing() -> None:
    node_a = _INTERP._edge_by_id("node_a")
    planned = _INTERP.plan_actions(node_a, current_tick=42)
    moves = [(p["agent"], p["to"]) for p in planned if p["type"] == "move_agent"]
    assert moves == [(2, "jensen_private_room")], moves  # routing node A：Jensen→私人房
    sets = [p for p in planned if p["type"] == "set_session"]
    assert sets == [{"type": "set_session", "field": "phase2_start_tick", "value": 42}], sets
    phases = [p["new_phase"] for p in planned if p["type"] == "advance_player_place"]
    assert phases == ["Phase 2"], phases

    node_b = _INTERP._edge_by_id("node_b")
    pb = _INTERP.plan_actions(node_b, current_tick=99)
    bmoves = [(p["agent"], p["to"]) for p in pb if p["type"] == "move_agent"]
    assert bmoves == [(2, "negotiation_room")], bmoves
    mut = [p for p in pb if p["type"] == "place_mutation"]
    assert len(mut) == 1 and "死一般的寂静" in mut[0]["behavior_hint"], mut

    node_c = _INTERP._edge_by_id("node_c")
    pc = _INTERP.plan_actions(node_c, current_tick=1)
    cmoves = sorted((p["agent"], p["to"]) for p in pc if p["type"] == "move_agent")
    assert cmoves == [(4, "nvidia_reception"), (5, "nvidia_reception"), (6, "nvidia_reception")], cmoves


# ---------------- signals.yaml 与 routing_config 不漂移守卫 ----------------
def test_signals_match_routing_config() -> None:
    from agent_world.hbm_demo.features.f05_story_routing import routing_config as RC
    from agent_world.hbm_demo.features.f05_story_routing.routing import POSITIVE_RDC_KEYWORDS

    ks = _INTERP._keyword_sets
    assert tuple(ks["approve_keywords"]) == RC.approve_keywords()
    assert tuple(ks["reject_keywords"]) == RC.reject_keywords()
    assert tuple(ks["expel_keywords"]) == RC.expel_keywords()
    assert tuple(ks["escort_keywords"]) == RC.escort_keywords()
    assert tuple(ks["return_to_negotiation_keywords"]) == RC.return_to_negotiation_keywords()
    assert tuple(ks["positive_rdc_keywords"]) == POSITIVE_RDC_KEYWORDS
    assert _INTERP._param("max_turns_phase1_without_approve") == RC.max_turns_phase1_without_approve()
    # G3 漂移守卫：解释器(signals.yaml)与旧路径(routing.yaml)的 story_advance.enabled 必须同源一致，
    # 否则开/关 HBM_STORY_PACK_ROUTING 节点推进条件不同，破坏等价性承诺。
    assert _INTERP._story_advance_enabled == RC.is_story_advance_enabled(), (
        "story_advance.enabled 双源漂移：signals.yaml 与 routing.yaml 不一致"
    )


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
    print(f"\ninterpreter 等价回归：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
