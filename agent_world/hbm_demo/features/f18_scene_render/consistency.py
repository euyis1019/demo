"""跨帧一致性：为每个房间的 t2i 锚定帧派生稳定 seed（同房间锚定帧风格稳定）。

角色一致由 render 的 img2img 链负责（以上一帧为参考）；此处只管锚定帧 seed。
"""

from __future__ import annotations

import zlib


def seed_for_place(place_id: str, seed_base: int) -> int:
    """同一房间恒定返回同一 seed；不同房间错开，避免画面互相串味。"""
    offset = zlib.crc32((place_id or "default").encode("utf-8")) % 1000
    return int(seed_base) + offset
