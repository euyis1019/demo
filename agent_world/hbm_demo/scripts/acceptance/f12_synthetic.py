#!/usr/bin/env python3
"""
F12 synthetic engine replay — no LLM, mimics agent/world behaviors (dev_logs/32 §八).

Directly seeds world.db (messages, moves, OS, group events, broadcasts) and validates:
- Flask build_world_delta / build_completed_payload / build_world_snapshot
- Incremental poll windows (like useGameLoop)
- HTTP GET /world-snapshot (Flask test client, no Runner)
- Frontend worldSync via fixtures/f12_synthetic_fixture.json + TS replay
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[4]
HBM_DIR = ROOT / "agent_world" / "hbm_demo"
FIXTURE_PATH = HBM_DIR / "scripts" / "fixtures" / "f12_synthetic_fixture.json"
SIM_ID = "hbm_memory_war"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask
from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.hbm_demo.features.f12_world_sync.constants import (
    HBM_ROOM_PLACES,
    ROUTING_WORLD_EVENT_CONTENT,
)
from agent_world.hbm_demo.features.f12_world_sync.delta import (
    build_completed_payload,
    build_world_delta,
)
from agent_world.hbm_demo.features.f12_world_sync.handler import get_world_snapshot
from agent_world.hbm_demo.features.f12_world_sync.snapshot import build_world_snapshot
from agent_world.hbm_demo.features.f01_session.models import HbmSession
from agent_world.persistence.world_db import WorldDB

RECEPTION = "nvidia_reception"
NEGOTIATION = "negotiation_room"
PRIVATE = "jensen_private_room"
OPENAI = "openai_hq"


class TestFailure(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Synthetic world timeline — mimics Runner agent actions without LLM
# ---------------------------------------------------------------------------


async def seed_synthetic_world(db: WorldDB, *, through_tick: int = 20) -> int:
    """Seed places, agents, messages, moves, OS, social events up to ``through_tick``."""
    for place_id in HBM_ROOM_PLACES:
        attrs = {"summary": place_id}
        if place_id == NEGOTIATION:
            attrs["tension"] = "high"
        await db.upsert_place(
            place_id,
            None,
            "room",
            attrs=json.dumps(attrs),
            capacity=10,
            created_at=0,
        )

    # Initial agent locations (Turn 0)
    for agent_id, place_id in (
        (1, RECEPTION),
        (2, NEGOTIATION),
        (3, NEGOTIATION),
        (4, NEGOTIATION),
        (5, NEGOTIATION),
        (6, NEGOTIATION),
        (7, OPENAI),
    ):
        await db.set_location(agent_id, place_id, t=0)

    # --- Turn1: 前台 F2F @ reception (§八 Turn1) ---
    if through_tick >= 2:
        await db.insert_message(
            sender_id=1,
            recipient_id=2,
            group_id=None,
            channel_type="F2F",
            content="欢迎来访 NVIDIA",
            place_id=RECEPTION,
            attempted_at=2,
            arrive_at=2,
            delivered=1,
        )

    # --- Jensen RDC→VP @ negotiation, no F2F there in same early window (§八) ---
    if through_tick >= 4:
        await db.insert_message(
            sender_id=2,
            recipient_id=3,
            group_id=None,
            channel_type="RDC",
            content="VP 这是 Roadmap 摘要",
            place_id="",
            attempted_at=4,
            arrive_at=4,
            delivered=1,
        )

    # --- Cross-room F2F @ negotiation (F12 grid shows it; old API hid this) ---
    if through_tick >= 6:
        await db.insert_message(
            sender_id=4,
            recipient_id=5,
            group_id=None,
            channel_type="F2F",
            content="谈判室背景 F2F",
            place_id=NEGOTIATION,
            attempted_at=6,
            arrive_at=6,
            delivered=1,
        )

    # --- CEO group + GRP ---
    gid = await db.insert_group("ceo_group")
    for aid in (4, 5, 6):
        await db.insert_group_member(gid, aid)
    if through_tick >= 5:
        await db.insert_message(
            sender_id=4,
            recipient_id=4,
            group_id=gid,
            channel_type="GRP",
            content="CEO 联盟群聊",
            place_id=NEGOTIATION,
            attempted_at=5,
            arrive_at=5,
            delivered=1,
        )

    # --- Node A: Jensen → private room (§八 节点 A) ---
    if through_tick >= 8:
        await db.insert_location_log(2, NEGOTIATION, PRIVATE, 8, "ipc_move")
        await db.set_location(2, PRIVATE, t=8)

    # --- update_state inner OS (§八) ---
    if through_tick >= 9:
        db.insert_state_log_sync(agent_id=2, content="内心：底牌在手", at_tick=9)

    # --- 群退 (§八) ---
    if through_tick >= 10:
        await db.insert_group_event(gid, 5, "leave", 10, actor_id=5)
        await db.delete_group_member(gid, 5)

    # --- Node B: Jensen back to negotiation + place attrs mutation ---
    if through_tick >= 12:
        await db.insert_location_log(2, PRIVATE, NEGOTIATION, 12, "request_move")
        await db.set_location(2, NEGOTIATION, t=12)
        await db.update_place_attrs(
            NEGOTIATION,
            {"summary": NEGOTIATION, "tension": "high", "silence": True},
        )

    # --- Turn16 broadcast (§八) ---
    if through_tick >= 16:
        await db.insert_message(
            sender_id=-1,
            recipient_id=2,
            group_id=None,
            channel_type="RDC",
            content="彭博：HBM 现货价格异动",
            place_id=NEGOTIATION,
            attempted_at=16,
            arrive_at=16,
            delivered=1,
        )

    # --- Node C: CEO 4/5/6 → reception (§八) ---
    if through_tick >= 18:
        for aid in (4, 5, 6):
            await db.insert_location_log(aid, NEGOTIATION, RECEPTION, 18, "script")
            await db.set_location(aid, RECEPTION, t=18)

    return gid


def _make_synthetic_db(*, through_tick: int = 20) -> Tuple[Path, ReadOnlyWorldDB, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="f12_synth_"))
    db_path = tmp / "world.db"
    wdb = WorldDB(str(db_path))
    wdb.init_schema()
    _run(seed_synthetic_world(wdb, through_tick=through_tick))
    env_path = tmp / "env_status.json"
    env_path.write_text(
        json.dumps({"current_tick": through_tick, "status": "running"}),
        encoding="utf-8",
    )
    return tmp, ReadOnlyWorldDB(db_path), tmp


def _task(
    *,
    start: int = 0,
    place: str = RECEPTION,
    phase: str = "Phase 1",
    turn: int = 1,
    ipc_end: int | None = None,
) -> PendingTask:
    return PendingTask(
        task_id="task-synth",
        start_tick=start,
        place_id=place,
        phase=phase,
        player_turn=turn,
        ipc_end_tick=ipc_end,
    )


def _name_map() -> Dict[int, str]:
    return {
        1: "接待前台",
        2: "Jensen",
        3: "Tech VP",
        4: "AMD CEO",
        5: "Intel CEO",
        6: "Samsung CEO",
        7: "Sam Altman",
    }


# ---------------------------------------------------------------------------
# Scenario tests mapped to dev_logs/32 §八
# ---------------------------------------------------------------------------


def test_turn1_reception_f2f_and_jensen_rdc() -> None:
    """§八 Turn1 前台 F2F + Jensen RDC→VP（谈判室无同期 F2F 增量）。"""
    _, ro, _ = _make_synthetic_db()
    nm = _name_map()
    task = _task()
    delta = build_world_delta(task, since_tick=0, effective_tick=5, db=ro, name_map=nm)

    reception = delta["room_f2f"].get(RECEPTION) or []
    negotiation = delta["room_f2f"].get(NEGOTIATION) or []
    if len(reception) != 1 or reception[0].get("content") != "欢迎来访 NVIDIA":
        raise TestFailure(f"Turn1 reception F2F wrong: {reception}")
    if len(negotiation) != 0:
        raise TestFailure(f"Turn1 window 0-5 should have no negotiation F2F: {negotiation}")

    rdc_2 = delta["agent_messages"].get("2", {}).get("rdc") or []
    rdc_3 = delta["agent_messages"].get("3", {}).get("rdc") or []
    if len(rdc_2) != 1 or len(rdc_3) != 1:
        raise TestFailure(f"Jensen/VP RDC missing: {delta['agent_messages']}")

    legacy = delta["public_messages"]
    if len(legacy) != len(reception):
        raise TestFailure("legacy public_messages must match reception room_f2f")
    ok("§八 Turn1 — reception F2F + Jensen→VP RDC, negotiation F2F empty in window")


def test_cross_room_f2f_visible_in_grid() -> None:
    """§八 F12 grid: 谈判室 F2F 在 tick 6 后对全房间可见。"""
    _, ro, _ = _make_synthetic_db()
    delta = build_world_delta(
        _task(), since_tick=5, effective_tick=7, db=ro, name_map=_name_map()
    )
    neg = delta["room_f2f"].get(NEGOTIATION) or []
    if len(neg) != 1 or "谈判室背景" not in neg[0].get("content", ""):
        raise TestFailure(f"negotiation F2F not in room_f2f: {neg}")
    ok("§八 cross-room F2F appears in negotiation room_f2f (F12 grid)")


def test_node_a_jensen_private_and_routing() -> None:
    """§八 节点 A — Jensen 移到私人室 + routing world_event。"""
    _, ro, _ = _make_synthetic_db(through_tick=9)
    task = _task(ipc_end=8)
    routing = {"nodes": ["A"], "place_id": PRIVATE}
    delta = build_world_delta(
        task,
        since_tick=5,
        effective_tick=9,
        db=ro,
        name_map=_name_map(),
        routing_info=routing,
    )

    moves = delta["location_changes"]
    if len(moves) != 1 or moves[0]["to_place"] != PRIVATE:
        raise TestFailure(f"Node A move wrong: {moves}")

    locs = delta["agent_locations"]
    if locs.get("2", {}).get("place_id") != PRIVATE:
        raise TestFailure(f"Jensen location wrong: {locs}")

    routes = [e for e in delta["world_events"] if e.get("kind") == "phase_route"]
    if len(routes) != 1 or ROUTING_WORLD_EVENT_CONTENT["A"] not in routes[0]["content"]:
        raise TestFailure(f"Node A routing event wrong: {routes}")

    states = delta["state_changes"]
    if len(states) != 1 or "底牌" not in states[0]["content"]:
        raise TestFailure(f"update_state missing: {states}")
    ok("§八 节点 A — location + routing world_event + inner OS")


def test_node_b_place_mutation_routing() -> None:
    """§八 节点 B — Jensen 回谈判室 + place_mutation 弹窗。"""
    _, ro, _ = _make_synthetic_db(through_tick=13)
    task = _task(ipc_end=12)
    routing = {"nodes": ["B"], "place_id": NEGOTIATION, "place_mutation": True}
    delta = build_world_delta(
        task,
        since_tick=9,
        effective_tick=13,
        db=ro,
        name_map=_name_map(),
        routing_info=routing,
    )

    moves = [m for m in delta["location_changes"] if m["agent_id"] == 2]
    if not moves or moves[-1]["to_place"] != NEGOTIATION:
        raise TestFailure(f"Node B Jensen move wrong: {moves}")

    mutations = [e for e in delta["world_events"] if e.get("kind") == "place_mutation"]
    routes = [e for e in delta["world_events"] if e.get("kind") == "phase_route"]
    if not mutations:
        raise TestFailure("place_mutation world_event missing")
    if not routes or ROUTING_WORLD_EVENT_CONTENT["B"] not in routes[0]["content"]:
        raise TestFailure(f"Node B route wrong: {routes}")
    ok("§八 节点 B — Jensen→谈判室 + place_mutation + phase_route")


def test_turn16_broadcast() -> None:
    """§八 Turn16 广播 — world_events broadcast。"""
    _, ro, _ = _make_synthetic_db(through_tick=16)
    delta = build_world_delta(
        _task(), since_tick=14, effective_tick=16, db=ro, name_map=_name_map()
    )
    broadcasts = [e for e in delta["world_events"] if e.get("kind") == "broadcast"]
    if len(broadcasts) != 1 or "彭博" not in broadcasts[0]["content"]:
        raise TestFailure(f"Turn16 broadcast wrong: {broadcasts}")
    ok("§八 Turn16 — broadcast world_event")


def test_group_leave_social_event() -> None:
    """§八 群退 — social_events group_leave。"""
    _, ro, _ = _make_synthetic_db(through_tick=11)
    delta = build_world_delta(
        _task(), since_tick=8, effective_tick=11, db=ro, name_map=_name_map()
    )
    social = delta["social_events"]
    if len(social) != 1 or social[0].get("kind") != "group_leave":
        raise TestFailure(f"group_leave missing: {social}")
    ok("§八 群退 — social_events group_leave")


def test_node_c_ceos_to_reception() -> None:
    """§八 节点 C — CEO 4/5/6 移到前台。"""
    _, ro, _ = _make_synthetic_db()
    task = _task(ipc_end=18)
    routing = {"nodes": ["C"], "place_id": RECEPTION}
    delta = build_world_delta(
        task,
        since_tick=15,
        effective_tick=20,
        db=ro,
        name_map=_name_map(),
        routing_info=routing,
    )

    ceo_moves = [m for m in delta["location_changes"] if m["agent_id"] in (4, 5, 6)]
    if len(ceo_moves) != 3:
        raise TestFailure(f"Node C CEO moves wrong: {ceo_moves}")

    locs = delta["agent_locations"]
    for aid in ("4", "5", "6"):
        if locs.get(aid, {}).get("place_id") != RECEPTION:
            raise TestFailure(f"CEO {aid} not at reception: {locs}")

    routes = [e for e in delta["world_events"] if e.get("kind") == "phase_route"]
    if not any(ROUTING_WORLD_EVENT_CONTENT["C"] in r.get("content", "") for r in routes):
        raise TestFailure(f"Node C route event missing: {routes}")
    ok("§八 节点 C — CEO 4/5/6 location_changes + agent_locations + route")


def test_incremental_poll_sequence() -> None:
    """Mimics useGameLoop: since_tick advances, no duplicate F2F on re-poll。"""
    _, ro, _ = _make_synthetic_db()
    task = _task()
    nm = _name_map()
    windows = [(0, 5), (5, 8), (8, 12), (12, 16), (16, 20)]
    since = 0
    seen_f2f_keys: set[tuple] = set()
    total_moves = 0

    for _i, (_a, end) in enumerate(windows):
        delta = build_world_delta(task, since_tick=since, effective_tick=end, db=ro, name_map=nm)
        since = int(delta["through_tick"])
        for place_msgs in (delta.get("room_f2f") or {}).values():
            for msg in place_msgs:
                key = (msg.get("attempted_at"), msg.get("sender_id"), msg.get("content", "")[:40])
                if key in seen_f2f_keys:
                    raise TestFailure(f"duplicate F2F on incremental poll: {key}")
                seen_f2f_keys.add(key)
        total_moves += len(delta.get("location_changes") or [])

    if total_moves < 4:
        raise TestFailure(f"expected multiple location_changes across polls, got {total_moves}")
    ok(f"incremental poll sequence — {len(windows)} windows, {total_moves} moves, no dup F2F")


def test_completed_payload_full_turn() -> None:
    _, ro, _ = _make_synthetic_db()
    task = _task()
    payload = build_completed_payload(
        task,
        effective_tick=20,
        db=ro,
        name_map=_name_map(),
        stats_update={"vision": 5, "execution": 3, "trust": 12, "burnout": 0},
        current_phase="Phase 1",
    )
    if payload.get("status") != "completed":
        raise TestFailure("completed status wrong")
    for key in (
        "room_f2f",
        "agent_messages",
        "agent_locations",
        "location_changes",
        "world_events",
    ):
        if key not in payload:
            raise TestFailure(f"completed missing {key}")
    ok("build_completed_payload full-turn F12 shape")


def test_world_snapshot_calibration() -> None:
    sim_dir, ro, _ = _make_synthetic_db()
    snap = build_world_snapshot(
        ro,
        _name_map(),
        sim_dir=sim_dir,
        t_now=20,
        player_place_id=RECEPTION,
    )
    if snap["through_tick"] != 20:
        raise TestFailure(f"through_tick wrong: {snap}")
    if "1" not in snap["agent_locations"]:
        raise TestFailure("agent_locations missing in snapshot")
    attrs = snap["place_attrs"].get(NEGOTIATION) or {}
    if not attrs.get("tension"):
        raise TestFailure(f"place_attrs missing mutation: {attrs}")
    ok("build_world_snapshot — locations + place_attrs + name_map")


def test_flask_http_world_snapshot() -> None:
    """Flask GET /world-snapshot without Runner/LLM."""
    sim_dir, _, _ = _make_synthetic_db(through_tick=20)
    from agent_world.hbm_demo.features.f01_session.constants import SESSION_KEY

    hbm = HbmSession(
        task_id="task-synth",
        start_tick=0,
        place_id=RECEPTION,
        phase="Phase 1",
        player_turn=1,
    )
    flask_session: Dict[str, Any] = {SESSION_KEY: {SIM_ID: hbm.to_dict()}}

    # Patch sim dir for this test (handler binds get_sim_dir at import time)
    import agent_world.hbm_demo.features.f01_session.paths as paths_mod
    import agent_world.hbm_demo.features.f06_read_model.world_db as wdb_mod
    import agent_world.hbm_demo.features.f12_world_sync.handler as handler_mod
    import agent_world.hbm_demo.shared.env_status as env_mod

    old_sim = paths_mod.get_sim_dir
    old_env = env_mod.read_env_status
    old_make = wdb_mod.make_readonly_db
    old_handler_sim = handler_mod.get_sim_dir
    old_handler_env = handler_mod.read_env_status
    old_handler_make = handler_mod.make_readonly_db

    def _sim_override(_config: str | None = None):  # noqa: ANN001
        return sim_dir

    def _env_override(_sim: Any) -> Dict[str, Any]:  # noqa: ANN001
        return json.loads((sim_dir / "env_status.json").read_text(encoding="utf-8"))

    def _make_override(_sim: Any):  # noqa: ANN001
        return ReadOnlyWorldDB(sim_dir / "world.db")

    paths_mod.get_sim_dir = _sim_override  # type: ignore[assignment]
    env_mod.read_env_status = _env_override  # type: ignore[assignment]
    wdb_mod.make_readonly_db = _make_override  # type: ignore[assignment]
    handler_mod.get_sim_dir = _sim_override  # type: ignore[assignment]
    handler_mod.read_env_status = _env_override  # type: ignore[assignment]
    handler_mod.make_readonly_db = _make_override  # type: ignore[assignment]

    try:
        data = get_world_snapshot(flask_session, sim_id=SIM_ID, sim_dir=sim_dir)
        if data.get("player_place_id") != RECEPTION:
            raise TestFailure(f"snapshot player_place wrong: {data}")
        if len(data.get("agent_locations") or {}) < 5:
            raise TestFailure(f"agent_locations too sparse: {data.get('agent_locations')}")

        from agent_world.app import create_app

        app = create_app()
        client = app.test_client()
        with client.session_transaction() as sess:
            sess.update(flask_session)
        resp = client.get(f"/api/hbm/simulations/{SIM_ID}/world-snapshot")
        if resp.status_code != 200:
            raise TestFailure(f"HTTP {resp.status_code}: {resp.get_json()}")
        body = resp.get_json() or {}
        if not body.get("success"):
            raise TestFailure(f"HTTP body not success: {body}")
        http_data = body.get("data") or {}
        if http_data.get("through_tick") != 20:
            raise TestFailure(f"HTTP snapshot tick wrong: {http_data}")
    finally:
        paths_mod.get_sim_dir = old_sim  # type: ignore[assignment]
        env_mod.read_env_status = old_env  # type: ignore[assignment]
        wdb_mod.make_readonly_db = old_make  # type: ignore[assignment]
        handler_mod.get_sim_dir = old_handler_sim  # type: ignore[assignment]
        handler_mod.read_env_status = old_handler_env  # type: ignore[assignment]
        handler_mod.make_readonly_db = old_handler_make  # type: ignore[assignment]

    ok("Flask GET /world-snapshot — handler + HTTP, no Runner/LLM")


def test_frontend_fixture_replay() -> None:
    """Frontend worldSync replays fixtures/f12_synthetic_fixture.json."""
    if not FIXTURE_PATH.is_file():
        raise TestFailure(f"missing fixture {FIXTURE_PATH}")
    ts_script = HBM_DIR / "web" / "scripts" / "test_f12_synthetic_fixture.ts"
    env = dict(os.environ)
    env.setdefault("VITE_WORLD_STREAM", "false")
    proc = subprocess.run(
        ["npx", "--yes", "tsx", str(ts_script)],
        cwd=str(HBM_DIR / "web"),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise TestFailure(proc.stdout + proc.stderr or "frontend fixture replay failed")
    ok("frontend worldSync fixture replay (TS)")


def test_flask_delta_matches_db_visibility() -> None:
    """Reuse visibility audit — synthetic DB has zero hidden messages."""
    from agent_world.hbm_demo.scripts.acceptance.f12_visibility import audit_f12_delta

    _, ro, _ = _make_synthetic_db()
    report = audit_f12_delta(
        ro,
        start_tick=0,
        end_tick=20,
        player_place=RECEPTION,
        name_map=_name_map(),
    )
    if report["hidden_count"] != 0:
        raise TestFailure(f"hidden messages under F12: {report['hidden_samples']}")
    ok(f"F12 visibility — {report['world_total']} DB messages, hidden=0")


def main() -> int:
    print("F12 synthetic engine replay (dev_logs/32 §八 — no LLM)")
    print("Mimics: F2F, RDC, GRP, broadcast, move, OS, group_leave, routing A/B/C\n")

    tests = (
        test_turn1_reception_f2f_and_jensen_rdc,
        test_cross_room_f2f_visible_in_grid,
        test_node_a_jensen_private_and_routing,
        test_node_b_place_mutation_routing,
        test_turn16_broadcast,
        test_group_leave_social_event,
        test_node_c_ceos_to_reception,
        test_incremental_poll_sequence,
        test_completed_payload_full_turn,
        test_world_snapshot_calibration,
        test_flask_http_world_snapshot,
        test_flask_delta_matches_db_visibility,
        test_frontend_fixture_replay,
    )

    failures: List[str] = []
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__}: {exc}")
            print(f"  ✗ {exc}")

    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nALL F12 SYNTHETIC SCENARIO TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
