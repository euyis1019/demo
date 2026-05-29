"""F06 display name helpers."""

from __future__ import annotations

from typing import Optional

SYSTEM_SENDER_NAME = "彭博终端"


def sender_display_name(sender_id: Optional[int], name_map: dict[int, str]) -> str:
    if sender_id is None:
        return "未知"
    sid = int(sender_id)
    if sid == -1:
        return SYSTEM_SENDER_NAME
    if sid == 0:
        return str(name_map.get(0, "玩家"))
    return name_map.get(sid, f"agent_{sid}")
