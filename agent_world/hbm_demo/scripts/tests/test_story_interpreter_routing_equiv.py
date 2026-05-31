#!/usr/bin/env python3
"""interpreter_routing 运行期等价回归（G0-Slice4，dev_logs/45 §6）。

证明：开关开启时 watcher 走的 apply_routing_via_interpreter，与旧 routing.apply_routing 在
**同一份世界状态**上产生**完全相同**的运行期副作用——IPC 调用序列（移动 agent / place_mutation
入队）+ session 变更（phase/place_id/phaseN_start_tick）+ routing_info 结构。无需起 Runner/Flask/LLM。

做法：monkeypatch ipc_helper 的 send_move_agent / send_enqueue_script_event 为记录器，
对每个场景分别用两条路径跑（各自独立 session 副本、同一假 db），逐项断言两路结果一致。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

from agent_world.hbm_demo.features.f05_story_routing import interpreter_routing, routing
from agent_world.hbm_demo.scripts.tests.test_story_interpreter_equiv import FakeDB

STORY_ID = "hbm_memory_war"
_INTERP = interpreter_routing.get_interpreter(STORY_ID)


class FakeSession:
    def __init__(self, phase: str, place_id: str, **kw: Any) -> None:
        self.phase = phase
        self.place_id = place_id
        self.start_tick = kw.get("start_tick", 0)
        self.player_turn = kw.get("player_turn", 1)
        self.phase2_start_tick = kw.get("phase2_start_tick")
        self.phase3_start_tick = kw.get("phase3_start_tick")
        self.phase4_start_tick = kw.get("phase4_start_tick")

    def snapshot(self) -> Tuple:
        return (self.phase, self.place_id, self.phase2_start_tick, self.phase3_start_tick)


def _run(path: str, session: FakeSession, db: FakeDB, tick: int) -> Tuple[List, Dict, Tuple]:
    """跑一条路径，返回 (IPC 记录, routing_info, session 快照)。monkeypatch ipc_helper。"""
    import agent_world.hbm_demo.http.ipc_helper as ipc

    rec: List[Tuple] = []
    orig_move, orig_enq = ipc.send_move_agent, ipc.send_enqueue_script_event

    def fake_move(client: Any, *, agent_id: int, place_id: str, timeout: float = 0) -> None:
        rec.append(("move", int(agent_id), str(place_id)))

    def fake_enq(client: Any, *, events: List[Dict], broadcast: Optional[Dict] = None, timeout: float = 0) -> None:
        rec.append(("enqueue", tuple((e.get("id"), e.get("effect")) for e in events)))

    ipc.send_move_agent = fake_move
    ipc.send_enqueue_script_event = fake_enq
    try:
        if path == "legacy":
            info = routing.apply_routing(
                session, ipc_client=None, db=db, task_id=f"route_{tick}",
                current_tick=tick, tick_count=1, ipc_timeout=1.0,
            )
        else:
            info = interpreter_routing.apply_routing_via_interpreter(
                _INTERP, session, ipc_client=None, db=db, task_id=f"route_{tick}",
                current_tick=tick, ipc_timeout=1.0,
            )
    finally:
        ipc.send_move_agent = orig_move
        ipc.send_enqueue_script_event = orig_enq
    return rec, info, session.snapshot()


def _assert_equiv(label: str, make_session, db: FakeDB, tick: int) -> None:
    rec_l, info_l, snap_l = _run("legacy", make_session(), db, tick)
    rec_n, info_n, snap_n = _run("pack", make_session(), db, tick)
    assert rec_l == rec_n, f"[{label}] IPC 调用不一致：\n  legacy={rec_l}\n  pack  ={rec_n}"
    assert info_l == info_n, f"[{label}] routing_info 不一致：\n  legacy={info_l}\n  pack  ={info_n}"
    assert snap_l == snap_n, f"[{label}] session 变更不一致：\n  legacy={snap_l}\n  pack  ={snap_n}"


def test_node_a_routing_equiv() -> None:
    db = (FakeDB().add_rdc(1, 2, "天才来了", at_t=3).add_rdc(2, 3, "帮我验证", at_t=4)
          .add_rdc(2, 1, "带进来，私人会议室见", at_t=5))
    _assert_equiv("节点A触发", lambda: FakeSession("Phase 1", "nvidia_reception", start_tick=0), db, 50)


def test_node_b_routing_equiv() -> None:
    db = FakeDB().add_rdc(3, 2, "理论上成立，是核武器", at_t=20)
    _assert_equiv(
        "节点B触发",
        lambda: FakeSession("Phase 2", "jensen_private_room", start_tick=0, phase2_start_tick=10),
        db, 50,
    )


def test_node_c_routing_equiv() -> None:
    db = FakeDB().add_f2f("negotiation_room", 2, "请离场，谈完了", at_t=30)
    _assert_equiv(
        "节点C触发",
        lambda: FakeSession("Phase 3", "negotiation_room", start_tick=0, phase3_start_tick=20),
        db, 50,
    )


def test_no_transition_equiv() -> None:
    # 空 db：两路都 no-op，routing_info 仅 {"nodes": []}
    _assert_equiv("无转移P1", lambda: FakeSession("Phase 1", "nvidia_reception", start_tick=0), FakeDB(), 50)
    _assert_equiv(
        "无转移P2",
        lambda: FakeSession("Phase 2", "jensen_private_room", start_tick=0, phase2_start_tick=10),
        FakeDB(), 50,
    )


def test_node_c_via_rdc_equiv() -> None:
    # 节点C 另一路径：Jensen→某 CEO RDC 驱逐
    db = FakeDB().add_rdc(2, 5, "你们出去", at_t=30)
    _assert_equiv(
        "节点C-RDC",
        lambda: FakeSession("Phase 3", "negotiation_room", start_tick=0, phase3_start_tick=20),
        db, 50,
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
    print(f"\ninterpreter_routing 运行期等价：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
