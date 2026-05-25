#!/usr/bin/env python3
"""F12 message visibility — assert build_world_delta exposes all DB messages (dev_logs/32 Phase 4)."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_world.hbm_demo.features.f02_player_turn.task import PendingTask
from agent_world.hbm_demo.features.f06_read_model.world_db import ReadOnlyWorldDB
from agent_world.hbm_demo.features.f12_world_sync.constants import HBM_ROOM_PLACES
from agent_world.hbm_demo.features.f12_world_sync.delta import build_world_delta
from agent_world.persistence.world_db import WorldDB

RECEPTION = "nvidia_reception"
NEGOTIATION = "negotiation_room"
SIM = ROOT / "agent_world" / "hbm_demo" / "sim" / "hbm_memory_war"


class TestFailure(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


MessageKey = Tuple[str, int, int, str]


def _msg_key(channel: str, attempted_at: int, sender_id: int, content: str) -> MessageKey:
    return (channel, int(attempted_at), int(sender_id), str(content)[:80])


def _collect_f12_message_keys(delta: Dict[str, Any]) -> Set[MessageKey]:
    visible: Set[MessageKey] = set()
    room_f2f = delta.get("room_f2f") or {}
    for place_id, messages in room_f2f.items():
        for msg in messages or []:
            sid = msg.get("sender_id")
            if sid is None:
                continue
            visible.add(
                _msg_key("F2F", msg.get("attempted_at") or 0, int(sid), msg.get("content") or "")
            )
            _ = place_id  # F2F keyed by sender; place validated separately

    for bucket in (delta.get("agent_messages") or {}).values():
        for msg in bucket.get("rdc") or []:
            sid = msg.get("sender_id")
            if sid is not None and int(sid) != -1:
                visible.add(
                    _msg_key(
                        "RDC",
                        msg.get("attempted_at") or 0,
                        int(sid),
                        msg.get("content") or "",
                    )
                )
        for msg in bucket.get("grp") or []:
            sid = msg.get("sender_id")
            if sid is not None:
                visible.add(
                    _msg_key(
                        "GRP",
                        msg.get("attempted_at") or 0,
                        int(sid),
                        msg.get("content") or "",
                    )
                )

    for msg in delta.get("observer_messages") or []:
        sid = msg.get("sender_id")
        if sid is not None and int(sid) != -1:
            visible.add(
                _msg_key("RDC", msg.get("attempted_at") or 0, int(sid), msg.get("content") or "")
            )
    for msg in delta.get("group_messages") or []:
        sid = msg.get("sender_id")
        if sid is not None:
            visible.add(
                _msg_key("GRP", msg.get("attempted_at") or 0, int(sid), msg.get("content") or "")
            )

    return visible


def _f2f_places_in_delta(delta: Dict[str, Any]) -> Dict[MessageKey, str]:
    out: Dict[MessageKey, str] = {}
    for place_id, messages in (delta.get("room_f2f") or {}).items():
        for msg in messages or []:
            sid = msg.get("sender_id")
            if sid is None:
                continue
            key = _msg_key("F2F", msg.get("attempted_at") or 0, int(sid), msg.get("content") or "")
            out[key] = str(place_id)
    return out


def audit_f12_delta(
    db: ReadOnlyWorldDB,
    *,
    start_tick: int,
    end_tick: int,
    player_place: str,
    name_map: Dict[int, str],
) -> Dict[str, Any]:
    task = PendingTask(
        task_id="vis-audit",
        start_tick=start_tick,
        place_id=player_place,
        phase="Phase 1",
        player_turn=1,
    )
    delta = build_world_delta(
        task, since_tick=start_tick, effective_tick=end_tick, db=db, name_map=name_map
    )
    visible = _collect_f12_message_keys(delta)
    f2f_places = _f2f_places_in_delta(delta)

    def _query(conn):  # noqa: ANN001
        return conn.execute(
            """
            SELECT attempted_at, channel_type, sender_id, recipient_id,
                   group_id, place_id, content, delivered
            FROM direct_message
            WHERE attempted_at > ? AND attempted_at <= ?
              AND delivered >= 0
            ORDER BY attempted_at, message_id
            """,
            (start_tick, end_tick),
        ).fetchall()

    rows = db._with_retry(_query)  # noqa: SLF001
    hidden: List[Dict[str, Any]] = []
    for row in rows:
        ch = str(row["channel_type"])
        at = int(row["attempted_at"])
        sid = int(row["sender_id"]) if row["sender_id"] is not None else -1
        content = str(row["content"] or "")
        key = _msg_key(ch, at, sid, content)

        if ch == "F2F":
            place_id = str(row["place_id"] or "")
            if place_id not in HBM_ROOM_PLACES:
                hidden.append(dict(row))
                continue
            if key not in visible:
                hidden.append(dict(row))
                continue
            if f2f_places.get(key) != place_id:
                hidden.append(dict(row))
            continue

        if ch in ("RDC", "GRP"):
            if sid == -1:
                # broadcasts surface via world_events, not agent_messages
                broadcasts = [
                    e for e in (delta.get("world_events") or []) if e.get("kind") == "broadcast"
                ]
                if not any(content[:40] in str(e.get("content") or "") for e in broadcasts):
                    hidden.append(dict(row))
                continue
            if key not in visible:
                hidden.append(dict(row))

    return {
        "start_tick": start_tick,
        "end_tick": end_tick,
        "player_place": player_place,
        "world_total": len(rows),
        "hidden_count": len(hidden),
        "hidden_samples": hidden[:5],
        "room_f2f_places": sum(len(v) for v in (delta.get("room_f2f") or {}).values()),
        "agent_message_agents": len(delta.get("agent_messages") or {}),
    }


async def _seed_cross_room(db: WorldDB) -> None:
    for place_id in HBM_ROOM_PLACES:
        await db.upsert_place(
            place_id,
            None,
            "room",
            attrs=json.dumps({"summary": place_id}),
            capacity=10,
            created_at=0,
        )
    await db.set_location(1, RECEPTION, t=0)
    await db.set_location(2, NEGOTIATION, t=0)
    await db.set_location(3, NEGOTIATION, t=0)
    await db.insert_message(
        sender_id=1,
        recipient_id=2,
        group_id=None,
        channel_type="F2F",
        content="接待室 F2F",
        place_id=RECEPTION,
        attempted_at=2,
        arrive_at=2,
        delivered=1,
    )
    await db.insert_message(
        sender_id=4,
        recipient_id=5,
        group_id=None,
        channel_type="F2F",
        content="谈判室 CEO 私下 F2F",
        place_id=NEGOTIATION,
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
    await db.insert_message(
        sender_id=4,
        recipient_id=4,
        group_id=gid,
        channel_type="GRP",
        content="CEO 群聊",
        place_id=NEGOTIATION,
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
        place_id=NEGOTIATION,
        attempted_at=7,
        arrive_at=7,
        delivered=1,
    )


def test_synthetic_no_hidden_under_f12() -> None:
    name_map = {1: "前台", 2: "Jensen", 3: "Tech VP", 4: "AMD CEO"}
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "world.db"
        wdb = WorldDB(str(db_path))
        wdb.init_schema()
        asyncio.run(_seed_cross_room(wdb))
        ro = ReadOnlyWorldDB(db_path)
        report = audit_f12_delta(
            ro,
            start_tick=0,
            end_tick=10,
            player_place=RECEPTION,
            name_map=name_map,
        )
        if report["hidden_count"] != 0:
            raise TestFailure(
                f"F12 should expose cross-room F2F/RDC/GRP/broadcast; hidden={report}"
            )
        if report["room_f2f_places"] < 2:
            raise TestFailure(f"expected F2F in 2+ rooms, got {report}")
    ok("F12 delta exposes cross-room F2F (negotiation) + RDC/GRP/broadcast — no hidden")


def test_legacy_player_place_would_hide_negotiation_f2f() -> None:
    """Document pre-F12 gap: player at reception only saw local F2F."""
    name_map = {4: "AMD CEO"}
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "world.db"
        wdb = WorldDB(str(db_path))
        wdb.init_schema()
        asyncio.run(_seed_cross_room(wdb))
        ro = ReadOnlyWorldDB(db_path)
        f2f_neg = ro.fetch_f2f_history_at(NEGOTIATION, 10, 0)
        f2f_rec = ro.fetch_f2f_history_at(RECEPTION, 10, 0)
        if len(f2f_neg) < 1 or len(f2f_rec) < 1:
            raise TestFailure("seed data missing F2F rows")
        # Old API: only reception public_messages
        old_public = [h for h in f2f_rec if h[0] > 0]
        if len(old_public) >= len(f2f_neg) + len(f2f_rec):
            raise TestFailure("legacy model should show fewer F2F than full grid")
    ok("pre-F12 player-place F2F filter would hide negotiation_room (F12 fixes this)")


def test_live_sim_if_present() -> None:
    db_path = SIM / "world.db"
    if not db_path.is_file():
        ok("live sim world.db absent — skip live visibility audit")
        return
    from agent_world.hbm_demo.features.f01_session.paths import get_name_map

    ro = ReadOnlyWorldDB(db_path)
    name_map = get_name_map()
    report = audit_f12_delta(
        ro,
        start_tick=0,
        end_tick=24,
        player_place=RECEPTION,
        name_map=name_map,
    )
    if report["hidden_count"] > 0:
        raise TestFailure(
            f"live world.db has F12 hidden messages: {report['hidden_samples']}"
        )
    ok(
        f"live sim tick 0–24 — {report['world_total']} messages, "
        f"hidden=0, room_f2f={report['room_f2f_places']}"
    )


def main() -> int:
    print("F12 message visibility audit (dev_logs/32 Phase 4)")
    tests = (
        test_synthetic_no_hidden_under_f12,
        test_legacy_player_place_would_hide_negotiation_f2f,
        test_live_sim_if_present,
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

    print("\nALL F12 VISIBILITY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
