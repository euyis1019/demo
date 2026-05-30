"""跨帧一致性：为每个房间派生稳定 seed（同房间跨 tick 不变 → 画面稳定）。

P0 只做 seed 锁定；参考图(IP-Adapter/ControlNet)留待 P4，pollinations 暂不支持。
"""

from __future__ import annotations

import zlib


def seed_for_place(place_id: str, seed_base: int) -> int:
    """同一房间恒定返回同一 seed；不同房间错开，避免画面互相串味。"""
    offset = zlib.crc32((place_id or "default").encode("utf-8")) % 1000
    return int(seed_base) + offset
