#!/usr/bin/env python3
"""群聊门控单测（需求三地基，f07_agent_control/group_gate.py）。纯只读，离线。

门控规则：玩家须先 F2F 见过某群成员（双向在场说话）、且该成员 F2F 同意（拒绝优先一票否决），
才能加入该群。用假只读 db 覆盖 met/未met、consent/reject/both 各分支。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Tuple

from agent_world.drama_demo.features.f07_agent_control.group_gate import (
    can_player_join_group,
    joinable_groups_for_player,
)

HALL = "hall"


class FakeDB:
    def __init__(self) -> None:
        self.groups: Dict[int, List[int]] = {}
        self.f2f: List[Tuple[str, int, str, int]] = []  # (place, sender, content, at_t)

    def group(self, gid: int, members: List[int]) -> "FakeDB":
        self.groups[gid] = members
        return self

    def f2f_say(self, place: str, sender: int, content: str, at_t: int = 5) -> "FakeDB":
        self.f2f.append((place, sender, content, at_t))
        return self

    def fetch_group_members(self) -> Dict[int, List[int]]:
        return dict(self.groups)

    def fetch_f2f_from_sender_at(self, place_id: str, sender_id: int, t_now: int, since_t: int, **kw: Any):
        return sorted(
            [(t, s, i, c) for i, (p, s, c, t) in enumerate(self.f2f)
             if p == place_id and s == sender_id and since_t <= t <= t_now],
            key=lambda r: r[0],
        )


def _can(db: FakeDB, gid: int) -> bool:
    return can_player_join_group(db, gid, player_place=HALL, since_t=0, t_now=100)


def test_met_and_consented_can_join() -> None:
    db = (FakeDB().group(100, [1, 2])
          .f2f_say(HALL, 0, "你好，我想加入你们")     # 玩家在场说话
          .f2f_say(HALL, 1, "欢迎，算你一个，进群吧"))  # 成员1 同意
    assert _can(db, 100) is True


def test_not_met_cannot_join() -> None:
    # 成员1 同意了，但玩家没在该场说过话（没见面）→ 不能加
    db = FakeDB().group(100, [1]).f2f_say(HALL, 1, "欢迎加入")
    assert _can(db, 100) is False


def test_met_but_rejected_cannot_join() -> None:
    db = (FakeDB().group(100, [1])
          .f2f_say(HALL, 0, "能让我加入吗")
          .f2f_say(HALL, 1, "不同意，没你的份"))  # 拒绝
    assert _can(db, 100) is False


def test_reject_priority_over_consent() -> None:
    # 同一成员先同意后反悔拒绝 → 拒绝一票否决
    db = (FakeDB().group(100, [1])
          .f2f_say(HALL, 0, "我想进群")
          .f2f_say(HALL, 1, "欢迎加入", at_t=5)
          .f2f_say(HALL, 1, "算了，不欢迎你", at_t=8))
    assert _can(db, 100) is False


def test_consent_without_meeting_place_mismatch() -> None:
    # 成员在别的地点同意，玩家不在同一地点 → 不算见过
    db = (FakeDB().group(100, [1])
          .f2f_say("other_room", 0, "你好")
          .f2f_say("other_room", 1, "欢迎加入"))
    assert _can(db, 100) is False  # player_place=hall，查不到 hall 的往来


def test_one_consenting_member_is_enough() -> None:
    # 群里两成员，只要一个见过+同意即可
    db = (FakeDB().group(200, [3, 4])
          .f2f_say(HALL, 0, "各位好")
          .f2f_say(HALL, 4, "我同意，一起聊"))   # 成员4 同意（成员3 没出现）
    assert _can(db, 200) is True


def test_joinable_groups_list() -> None:
    db = (FakeDB()
          .group(100, [1]).group(200, [2])
          .f2f_say(HALL, 0, "你们好")
          .f2f_say(HALL, 1, "欢迎加入"))  # 只有群100可加
    assert joinable_groups_for_player(db, player_place=HALL, since_t=0, t_now=100) == [100]


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
    print(f"\n群聊门控：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
