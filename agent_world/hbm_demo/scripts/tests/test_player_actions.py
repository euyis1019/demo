#!/usr/bin/env python3
"""玩家主动动作单测（需求二：私信RDC/加群GRP 的 payload 构造与落地）。离线，假 db/grp_bus。"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f17_virtual_player.player_actions import (
    apply_player_grp_payload,
    apply_player_rdc_payload,
    build_player_grp_payload,
    build_player_rdc_payload,
)


class FakeSession:
    def __init__(self, place_id: str = "negotiation_room") -> None:
        self.place_id = place_id


class FakeWorldDB:
    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    async def insert_message(self, **kw: Any) -> int:
        self.messages.append(kw)
        return len(self.messages)


class FakeGrpBus:
    def __init__(self) -> None:
        self.joined: List[tuple] = []
        self.sent: List[tuple] = []

    async def join_group(self, agent_id: int, group_id: int) -> bool:
        # 与真实 GroupMessageBus.join_group(agent_id, group_id) 签名一致，防假桩漂绿。
        self.joined.append((agent_id, group_id))
        return True

    async def send_to_group(self, sender: int, gid: int, content: str, t: int) -> int:
        self.sent.append((sender, gid, content, t))
        return 1


def test_build_rdc_payload() -> None:
    p = build_player_rdc_payload(FakeSession(), 3, "悄悄告诉你一件事")
    assert p and p["sender_id"] == 0 and p["recipient_id"] == 3
    assert p["place_id"] == "negotiation_room" and p["content"]
    assert build_player_rdc_payload(FakeSession(), 3, "   ") is None  # 空内容


def test_apply_rdc_inserts_rdc_row() -> None:
    db = FakeWorldDB()
    payload = build_player_rdc_payload(FakeSession(), 2, "我想私下谈谈")
    mid = asyncio.run(apply_player_rdc_payload(db, payload, t=7))
    assert mid == 1 and len(db.messages) == 1
    m = db.messages[0]
    assert m["channel_type"] == "RDC" and m["sender_id"] == 0 and m["recipient_id"] == 2
    assert m["group_id"] is None and m["delivered"] == 1  # 即时投递


def test_apply_rdc_skips_empty() -> None:
    db = FakeWorldDB()
    assert asyncio.run(apply_player_rdc_payload(db, None, t=1)) is None
    assert len(db.messages) == 0


def test_build_grp_payload() -> None:
    p = build_player_grp_payload(FakeSession(), 100, "大家好我加进来了")
    assert p and p["sender_id"] == 0 and p["group_id"] == 100 and p["content"]
    assert build_player_grp_payload(FakeSession(), None) is None


def test_apply_grp_joins_and_sends() -> None:
    bus = FakeGrpBus()
    payload = build_player_grp_payload(FakeSession(), 100, "各位好")
    ok = asyncio.run(apply_player_grp_payload(FakeWorldDB(), bus, payload, t=9))
    assert ok is True
    assert bus.joined == [(0, 100)]            # 入群(agent_id=0, group_id=100)，顺序与真实总线一致
    assert bus.sent and bus.sent[0][:3] == (0, 100, "各位好")


def test_apply_grp_join_only_no_content() -> None:
    bus = FakeGrpBus()
    payload = build_player_grp_payload(FakeSession(), 200, "")  # 只加群不发言
    ok = asyncio.run(apply_player_grp_payload(FakeWorldDB(), bus, payload, t=3))
    assert ok is True and bus.joined == [(0, 200)] and bus.sent == []


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
    print(f"\n玩家动作：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
