#!/usr/bin/env python3
"""F12 Phase 1 — Runner persistence audit logs (dev_logs/32 §七 Phase 1)."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_world.persistence.world_db import WorldDB
from agent_world.world.clock import Clock
from agent_world.world.place_store import PlaceStore
from agent_world.world.state import WorldState


class TestFailure(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _seed_places(db: WorldDB, store: PlaceStore) -> None:
    async def _run() -> None:
        await db.upsert_place(
            "nvidia_reception",
            None,
            "room",
            attrs=json.dumps({"summary": "reception"}),
            capacity=10,
            created_at=0,
        )
        await db.upsert_place(
            "jensen_private_room",
            None,
            "room",
            attrs=json.dumps({"summary": "private"}),
            capacity=3,
            created_at=0,
        )
        await db.set_location(1, "nvidia_reception", t=0)

    asyncio.run(_run())
    store.load_from_db(db)


def test_schema_tables_exist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        tables = {
            row[0]
            for row in db._exec(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for name in ("agent_location_log", "agent_state_log"):
            if name not in tables:
                raise TestFailure(f"missing table {name}")
    ok("DDL creates agent_location_log and agent_state_log")


def test_move_writes_location_log() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        store = PlaceStore(db)
        _seed_places(db, store)

        async def _run() -> None:
            await store.move(1, "jensen_private_room", t=5, source="ipc_move")

        asyncio.run(_run())

        rows = db.fetch_location_logs_since(0, 10)
        if len(rows) != 1:
            raise TestFailure(f"expected 1 location log, got {len(rows)}")
        row = rows[0]
        if row["agent_id"] != 1:
            raise TestFailure(f"agent_id mismatch: {row}")
        if row["from_place"] != "nvidia_reception":
            raise TestFailure(f"from_place mismatch: {row}")
        if row["to_place"] != "jensen_private_room":
            raise TestFailure(f"to_place mismatch: {row}")
        if row["at_tick"] != 5:
            raise TestFailure(f"at_tick mismatch: {row}")
        if row["source"] != "ipc_move":
            raise TestFailure(f"source mismatch: {row}")
        loc = db.get_location(1)
        if not loc or loc["place_id"] != "jensen_private_room":
            raise TestFailure(f"agent_location not updated: {loc}")
    ok("place_store.move persists agent_location_log")


def test_update_state_writes_state_log() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        store = PlaceStore(db)
        clock = Clock(t0=3)
        world = WorldState(
            db,
            store,
            relations=_StubRelations(),
            caps=_StubCaps(),
            clock=clock,
            pool_manager=_StubPools(),
        )
        world.set_current_state(2, "内心：震惊", t=7)
        rows = db.fetch_state_logs_since(0, 10, agent_id=2)
        if len(rows) != 1:
            raise TestFailure(f"expected 1 state log, got {len(rows)}")
        if rows[0]["content"] != "内心：震惊":
            raise TestFailure(f"content mismatch: {rows[0]}")
        if rows[0]["at_tick"] != 7:
            raise TestFailure(f"at_tick mismatch: {rows[0]}")
    ok("WorldState.set_current_state persists agent_state_log")


def test_update_place_attrs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()

        async def _run() -> None:
            await db.upsert_place(
                "negotiation_room",
                None,
                "room",
                attrs=json.dumps({"behavior_hint": "火药味"}),
                capacity=10,
                created_at=0,
            )
            await db.update_place_attrs(
                "negotiation_room",
                {"behavior_hint": "死一般的寂静…"},
            )

        asyncio.run(_run())
        raw = db.get_place_attrs("negotiation_room")
        data = json.loads(raw or "{}")
        if data.get("behavior_hint") != "死一般的寂静…":
            raise TestFailure(f"attrs not merged: {data}")
    ok("update_place_attrs merges place.attrs in DB")


def test_clear_logs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        db.insert_state_log_sync(1, "x", 1)
        asyncio.run(
            db.insert_location_log(1, "a", "b", 1, "ipc_move")
        )
        db.clear_state_logs()
        db.clear_location_logs()
        if db.fetch_state_logs_since(0, 10):
            raise TestFailure("state logs not cleared")
        if db.fetch_location_logs_since(0, 10):
            raise TestFailure("location logs not cleared")
    ok("clear_state_logs / clear_location_logs work")


def test_ipc_helper_list_places() -> None:
    from agent_world.hbm_demo.http import ipc_helper

    if not hasattr(ipc_helper, "fetch_list_places"):
        raise TestFailure("fetch_list_places missing from ipc_helper")
    ok("ipc_helper.fetch_list_places exported")


def test_f12_registry() -> None:
    from agent_world.hbm_demo.features import FEATURE_REGISTRY

    f12 = FEATURE_REGISTRY.get("F12")
    if not f12 or f12.get("status") != "in_progress":
        raise TestFailure(f"F12 registry wrong status: {f12}")
    if "f12_world_sync" not in str(f12.get("path", "")):
        raise TestFailure(f"F12 registry missing path: {f12}")
    ok("FEATURE_REGISTRY F12 registered")


def test_request_move_via_dispatcher() -> None:
    from agent_world.world.dispatcher import ActionDispatcher

    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        store = PlaceStore(db)
        _seed_places(db, store)
        world = WorldState(
            db,
            store,
            relations=_StubRelations(),
            caps=_StubCaps(),
            clock=Clock(t0=4),
            pool_manager=_StubPools(),
        )
        dispatcher = ActionDispatcher(
            world, None, None, None, _StubPools(), None
        )
        dispatcher.enqueue_move(1, "jensen_private_room", t=4)

        async def _run() -> None:
            results = await dispatcher.commit_pending_moves(t=4)
            if not results or not results[0].get("success"):
                raise TestFailure(f"commit_pending_moves failed: {results}")

        asyncio.run(_run())
        rows = db.fetch_location_logs_since(0, 10)
        if len(rows) != 1 or rows[0]["source"] != "request_move":
            raise TestFailure(f"expected request_move log: {rows}")
    ok("dispatcher.commit_pending_moves writes request_move log")


def test_move_effect_script_source() -> None:
    from agent_world.script.effects.move import MoveEffect

    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        store = PlaceStore(db)
        _seed_places(db, store)
        world = WorldState(
            db,
            store,
            relations=_StubRelations(),
            caps=_StubCaps(),
            clock=Clock(t0=9),
            pool_manager=_StubPools(),
        )

        async def _run() -> None:
            await MoveEffect(agent_id=1, place_id="jensen_private_room").apply(
                world
            )

        asyncio.run(_run())
        rows = db.fetch_location_logs_since(0, 20)
        if len(rows) != 1 or rows[0]["source"] != "script":
            raise TestFailure(f"expected script move log: {rows}")
    ok("MoveEffect.apply writes script source location log")


def test_place_mutation_effect_persists_db() -> None:
    from agent_world.script.effects.place_mutation import PlaceMutationEffect

    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        store = PlaceStore(db)

        async def _seed() -> None:
            await db.upsert_place(
                "negotiation_room",
                None,
                "room",
                attrs=json.dumps({"behavior_hint": "火药味"}),
                capacity=10,
                created_at=0,
            )

        asyncio.run(_seed())
        store.load_from_db(db)
        world = WorldState(
            db,
            store,
            relations=_StubRelations(),
            caps=_StubCaps(),
            clock=Clock(t0=1),
            pool_manager=_StubPools(),
        )
        patch = {"behavior_hint": "死一般的寂静…"}

        async def _run() -> None:
            await PlaceMutationEffect(
                place_id="negotiation_room", attrs_patch=patch
            ).apply(world)

        asyncio.run(_run())
        mem = store.places["negotiation_room"].attrs.get("behavior_hint")
        if mem != patch["behavior_hint"]:
            raise TestFailure(f"in-memory attrs not updated: {mem}")
        raw = db.get_place_attrs("negotiation_room")
        data = json.loads(raw or "{}")
        if data.get("behavior_hint") != patch["behavior_hint"]:
            raise TestFailure(f"DB attrs not updated: {data}")
    ok("PlaceMutationEffect updates memory + place.attrs in DB")


def test_state_change_effect_writes_log() -> None:
    from agent_world.script.effects.state_change import StateChangeEffect

    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        store = PlaceStore(db)
        world = WorldState(
            db,
            store,
            relations=_StubRelations(),
            caps=_StubCaps(),
            clock=Clock(t0=11),
            pool_manager=_StubPools(),
        )

        async def _run() -> None:
            await StateChangeEffect(
                agent_id=3, new_state="推演：算法成立"
            ).apply(world)

        asyncio.run(_run())
        rows = db.fetch_state_logs_since(0, 20, agent_id=3)
        if len(rows) != 1 or rows[0]["content"] != "推演：算法成立":
            raise TestFailure(f"StateChangeEffect log missing: {rows}")
    ok("StateChangeEffect writes agent_state_log via set_current_state")


def test_world_reset_clears_log_tables() -> None:
    from agent_world.hbm_demo.features.f01_session import world_reset

    volatile = world_reset._VOLATILE_TABLES
    for table in (
        "agent_location_log",
        "agent_state_log",
        "agent_llm_trace",
        "agent_action_trace_link",
        "group_event",
        "group_member",
        "capability",
    ):
        if table not in volatile:
            raise TestFailure(f"{table} not in world_reset._VOLATILE_TABLES")
    ok("world_reset._VOLATILE_TABLES includes F12 log tables")


def test_schema_idempotent_on_reinit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "world.db"
        db = WorldDB(str(path))
        db.init_schema()
        db.init_schema()
        tables = {
            row[0]
            for row in db._exec(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "agent_location_log" not in tables:
            raise TestFailure("re-init lost agent_location_log")
    ok("init_schema idempotent with F12 tables")


def test_fetch_since_tick_window() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = WorldDB(str(Path(tmp) / "world.db"))
        db.init_schema()
        db.insert_state_log_sync(1, "a", 3)
        db.insert_state_log_sync(1, "b", 5)
        db.insert_state_log_sync(1, "c", 8)
        mid = db.fetch_state_logs_since(3, 7, agent_id=1)
        if len(mid) != 1 or mid[0]["content"] != "b":
            raise TestFailure(f"since window wrong: {mid}")
    ok("fetch_state_logs_since respects since_tick/t_now window")


class _StubRelations:
    def contacts_of(self, agent_id: int):  # noqa: ARG002
        return []


class _StubCaps:
    def has(self, agent_id: int, cap: str) -> bool:  # noqa: ARG002
        return True


class _StubPools:
    pass


def main() -> int:
    print("F12 Phase 1 — Runner persistence tests (dev_logs/32)")
    failures: list[str] = []
    for fn in (
        test_schema_tables_exist,
        test_schema_idempotent_on_reinit,
        test_move_writes_location_log,
        test_request_move_via_dispatcher,
        test_move_effect_script_source,
        test_update_state_writes_state_log,
        test_state_change_effect_writes_log,
        test_update_place_attrs,
        test_place_mutation_effect_persists_db,
        test_clear_logs,
        test_world_reset_clears_log_tables,
        test_fetch_since_tick_window,
        test_ipc_helper_list_places,
        test_f12_registry,
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__}: {exc}")
            print(f"  ✗ {exc}")

    print("\n" + "=" * 50)
    if failures:
        print(f"FAILED ({len(failures)} issues):")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("ALL F12 PHASE 1 TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
