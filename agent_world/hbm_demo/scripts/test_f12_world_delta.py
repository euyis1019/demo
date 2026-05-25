#!/usr/bin/env python3
"""F12 Phase 2 — Flask world delta + world-snapshot (dev_logs/32 §七 Phase 2)."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask
from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.hbm_demo.features.f12_world_sync.constants import HBM_ROOM_PLACES
from agent_world.hbm_demo.features.f12_world_sync.delta import (
    build_completed_payload,
    build_world_delta,
    empty_delta,
)
from agent_world.hbm_demo.features.f12_world_sync.snapshot import build_world_snapshot
from agent_world.persistence.world_db import WorldDB


class TestFailure(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _seed_world(db: WorldDB) -> None:
    for place_id in HBM_ROOM_PLACES:
        await db.upsert_place(
            place_id,
            None,
            "room",
            attrs=json.dumps({"summary": place_id}),
            capacity=10,
            created_at=0,
        )
    for agent_id, place_id in (
        (1, "nvidia_reception"),
        (2, "negotiation_room"),
        (3, "negotiation_room"),
        (4, "negotiation_room"),
    ):
        await db.set_location(agent_id, place_id, t=0)

    await db.insert_message(
        sender_id=1,
        recipient_id=2,
        group_id=None,
        channel_type="F2F",
        content="接待室你好",
        place_id="nvidia_reception",
        attempted_at=2,
        arrive_at=2,
        delivered=1,
    )
    await db.insert_message(
        sender_id=2,
        recipient_id=1,
        group_id=None,
        channel_type="F2F",
        content="谈判室私下聊",
        place_id="negotiation_room",
        attempted_at=4,
        arrive_at=4,
        delivered=1,
    )
    await db.insert_message(
        sender_id=2,
        recipient_id=3,
        group_id=None,
        channel_type="RDC",
        content="Jensen 内参",
        place_id="",
        attempted_at=5,
        arrive_at=5,
        delivered=1,
    )
    gid = await db.insert_group("ceo_group")
    await db.insert_group_member(gid, 4)
    await db.insert_group_member(gid, 5)
    await db.insert_message(
        sender_id=4,
        recipient_id=4,
        group_id=gid,
        channel_type="GRP",
        content="CEO 群聊",
        place_id="negotiation_room",
        attempted_at=6,
        arrive_at=6,
        delivered=1,
    )
    await db.insert_message(
        sender_id=-1,
        recipient_id=2,
        group_id=None,
        channel_type="RDC",
        content="彭博终端快讯",
        place_id="negotiation_room",
        attempted_at=7,
        arrive_at=7,
        delivered=1,
    )
    await db.insert_location_log(
        agent_id=2,
        from_place="negotiation_room",
        to_place="jensen_private_room",
        at_tick=8,
        source="ipc_move",
    )
    await db.set_location(2, "jensen_private_room", t=8)
    db.insert_state_log_sync(agent_id=2, content="内心：底牌在手", at_tick=9)
    await db.insert_group_event(
        group_id=gid,
        agent_id=5,
        event_type="leave",
        occurred_at=10,
        actor_id=5,
    )


def _make_db() -> tuple[Path, ReadOnlyWorldDB]:
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "world.db"
    wdb = WorldDB(str(db_path))
    wdb.init_schema()
    _run(_seed_world(wdb))
    return db_path, ReadOnlyWorldDB(db_path)


def test_empty_delta_fields() -> None:
    ed = empty_delta(5, player_place_id="nvidia_reception")
    required = (
        "through_tick",
        "player_place_id",
        "room_f2f",
        "agent_messages",
        "location_changes",
        "social_events",
        "state_changes",
        "world_events",
        "agent_locations",
        "public_messages",
        "observer_messages",
        "group_messages",
    )
    for key in required:
        if key not in ed:
            raise TestFailure(f"empty_delta missing {key}")
    if len(ed["room_f2f"]) != len(HBM_ROOM_PLACES):
        raise TestFailure(f"room_f2f places count wrong: {ed['room_f2f']}")
    ok("empty_delta exposes all F12 + legacy fields")


def test_build_world_delta_content() -> None:
    _, ro = _make_db()
    name_map = {1: "前台", 2: "Jensen", 3: "Tech VP", 4: "AMD CEO"}
    task = PendingTask(
        task_id="t-f12",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
    )
    delta = build_world_delta(task, since_tick=1, effective_tick=10, db=ro, name_map=name_map)

    if delta["through_tick"] != 10:
        raise TestFailure(f"through_tick wrong: {delta['through_tick']}")
    if delta["player_place_id"] != "nvidia_reception":
        raise TestFailure(f"player_place_id wrong: {delta}")

    reception = delta["room_f2f"].get("nvidia_reception") or []
    negotiation = delta["room_f2f"].get("negotiation_room") or []
    if len(reception) != 1 or reception[0].get("content") != "接待室你好":
        raise TestFailure(f"reception F2F wrong: {reception}")
    if len(negotiation) != 1 or negotiation[0].get("content") != "谈判室私下聊":
        raise TestFailure(f"negotiation F2F wrong: {negotiation}")

    rdc_agents = delta["agent_messages"]
    if "3" not in rdc_agents or len(rdc_agents["3"]["rdc"]) != 1:
        raise TestFailure(f"agent 3 RDC missing: {rdc_agents}")
    if "4" not in rdc_agents or len(rdc_agents["4"]["grp"]) != 1:
        raise TestFailure(f"agent 4 GRP missing: {rdc_agents}")

    if len(delta["location_changes"]) != 1:
        raise TestFailure(f"location_changes wrong: {delta['location_changes']}")
    loc = delta["location_changes"][0]
    if loc["agent_id"] != 2 or loc["to_place"] != "jensen_private_room":
        raise TestFailure(f"location change wrong: {loc}")

    if len(delta["state_changes"]) != 1:
        raise TestFailure(f"state_changes wrong: {delta['state_changes']}")

    social = delta["social_events"]
    if len(social) != 1 or social[0].get("kind") != "group_leave":
        raise TestFailure(f"social_events wrong: {social}")

    broadcasts = [e for e in delta["world_events"] if e.get("kind") == "broadcast"]
    if len(broadcasts) != 1:
        raise TestFailure(f"broadcast world_events wrong: {delta['world_events']}")

    if "2" not in delta["agent_locations"]:
        raise TestFailure(f"agent_locations missing Jensen: {delta['agent_locations']}")

    if len(delta["public_messages"]) != len(reception):
        raise TestFailure("legacy public_messages != reception room_f2f")
    if len(delta["observer_messages"]) < 1:
        raise TestFailure("legacy observer_messages empty")
    if len(delta["group_messages"]) < 1:
        raise TestFailure("legacy group_messages empty")

    ok("build_world_delta room_f2f / agent_messages / logs / legacy compat")


def test_routing_world_events_window() -> None:
    _, ro = _make_db()
    name_map = {2: "Jensen"}
    routing = {"nodes": ["A"], "place_id": "jensen_private_room"}
    task = PendingTask(
        task_id="t-route",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 2",
        player_turn=2,
        ipc_end_tick=8,
        routing_info=routing,
    )

    inside = build_world_delta(
        task, since_tick=5, effective_tick=10, db=ro, name_map=name_map
    )
    routes_inside = [
        e for e in inside["world_events"] if e.get("kind") == "phase_route"
    ]
    if len(routes_inside) != 1:
        raise TestFailure(f"expected routing event in window: {inside['world_events']}")

    outside = build_world_delta(
        task, since_tick=9, effective_tick=10, db=ro, name_map=name_map
    )
    routes_outside = [
        e for e in outside["world_events"] if e.get("kind") == "phase_route"
    ]
    if routes_outside:
        raise TestFailure(
            f"routing event should not repeat outside ipc window: {routes_outside}"
        )
    ok("routing world_events only when since_t < ipc_end_tick <= t_now")


def test_build_completed_payload() -> None:
    _, ro = _make_db()
    name_map = {1: "前台", 2: "Jensen", 3: "Tech VP", 4: "AMD CEO"}
    task = PendingTask(
        task_id="t-done",
        start_tick=0,
        place_id="nvidia_reception",
        phase="Phase 1",
        player_turn=1,
    )
    payload = build_completed_payload(
        task,
        effective_tick=10,
        db=ro,
        name_map=name_map,
        stats_update={"trust": 50},
        current_phase="Phase 1",
    )
    if payload.get("status") != "completed":
        raise TestFailure(f"status wrong: {payload.get('status')}")
    if payload.get("end_tick") != 10:
        raise TestFailure(f"end_tick wrong: {payload.get('end_tick')}")
    if "room_f2f" not in payload or "agent_locations" not in payload:
        raise TestFailure(f"completed missing F12 keys: {payload.keys()}")
    ok("build_completed_payload merges F12 delta into completed response")


def test_build_world_snapshot() -> None:
    db_path, ro = _make_db()
    name_map = {1: "前台", 2: "Jensen"}
    snap = build_world_snapshot(
        ro,
        name_map,
        sim_dir=db_path.parent,
        since_tick=0,
        t_now=10,
        player_place_id="nvidia_reception",
    )
    for key in (
        "through_tick",
        "player_place_id",
        "agent_locations",
        "place_attrs",
        "relations",
        "group_members",
        "name_map",
    ):
        if key not in snap:
            raise TestFailure(f"snapshot missing {key}: {snap.keys()}")
    if snap["through_tick"] != 10:
        raise TestFailure(f"snapshot through_tick wrong: {snap}")
    if "2" not in snap["agent_locations"]:
        raise TestFailure(f"snapshot agent_locations wrong: {snap}")
    ok("build_world_snapshot read-model shape")


def test_f06_read_queries() -> None:
    _, ro = _make_db()
    locs = ro.fetch_all_agent_locations()
    if locs.get(2, {}).get("place_id") != "jensen_private_room":
        raise TestFailure(f"fetch_all_agent_locations wrong: {locs}")

    f2f = ro.fetch_f2f_by_places(1, 10, list(HBM_ROOM_PLACES))
    if not f2f.get("nvidia_reception"):
        raise TestFailure(f"fetch_f2f_by_places wrong: {f2f}")

    rdc = ro.fetch_rdc_for_agent(3, 1, 10)
    if len(rdc) != 1:
        raise TestFailure(f"fetch_rdc_for_agent wrong: {len(rdc)}")

    grp = ro.fetch_grp_for_agent(4, 1, 10)
    if len(grp) != 1:
        raise TestFailure(f"fetch_grp_for_agent wrong: {len(grp)}")

    events = ro.fetch_group_events_since(1, 10)
    if len(events) != 1:
        raise TestFailure(f"fetch_group_events_since wrong: {events}")

    logs = ro.fetch_location_logs_since(1, 10)
    if len(logs) != 1:
        raise TestFailure(f"fetch_location_logs_since wrong: {logs}")

    states = ro.fetch_state_logs_since(1, 10)
    if len(states) != 1:
        raise TestFailure(f"fetch_state_logs_since wrong: {states}")

    broadcasts = ro.fetch_broadcasts_since(1, 10)
    if len(broadcasts) != 1:
        raise TestFailure(f"fetch_broadcasts_since wrong: {broadcasts}")

    attrs = ro.fetch_place_attrs(list(HBM_ROOM_PLACES))
    if "nvidia_reception" not in attrs:
        raise TestFailure(f"fetch_place_attrs wrong: {attrs}")

    ok("F06 ReadOnlyWorldDB F12 query methods")


def main() -> int:
    print("F12 Phase 2 — Flask world delta tests")
    tests = (
        test_empty_delta_fields,
        test_f06_read_queries,
        test_build_world_delta_content,
        test_routing_world_events_window,
        test_build_completed_payload,
        test_build_world_snapshot,
    )
    failures: list[str] = []
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

    print("\nALL F12 PHASE 2 TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
