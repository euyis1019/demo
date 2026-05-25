"""``PlaceMutationEffect`` —— 局部更新某 place 的属性 dict。

按用户规范 MVP 版本：直接修改 ``world.places.attrs``（PlaceStore 暴露
的内存态），不写 world.db、不重建 connectivity 反向索引；后续 L2 阶段
可串接 ``world.world_db.update_place_attrs`` + ``connectivity.refresh``。
"""

from __future__ import annotations

from typing import Any, Dict

from agent_world.script._registrars import EffectBase


class PlaceMutationEffect(EffectBase):
    """Patch a place's in-memory ``attrs`` dict.

    Args:
        place_id: Target place ID.
        attrs_patch: Partial dict merged shallow-style into
            ``world.places.attrs[place_id]``. Keys present in
            ``attrs_patch`` overwrite existing values; other keys are
            preserved.
    """

    def __init__(self, *, place_id: str, attrs_patch: Dict[str, Any]) -> None:
        if not isinstance(attrs_patch, dict):
            raise TypeError("attrs_patch must be a dict")
        self.place_id = str(place_id)
        self.attrs_patch = dict(attrs_patch)

    async def apply(self, world: Any) -> None:
        places = getattr(world, "places", None)
        if places is None:
            raise RuntimeError("PlaceMutationEffect requires world.places")

        patch_fn = getattr(places, "patch_attrs", None) or getattr(
            places, "update_attrs", None
        )
        if callable(patch_fn):
            result = patch_fn(self.place_id, self.attrs_patch)
            if hasattr(result, "__await__"):
                await result
        elif hasattr(places, "places"):
            rec = places.places.get(self.place_id)
            if rec is not None:
                rec.attrs.update(self.attrs_patch)
            else:
                raise KeyError(f"unknown place_id: {self.place_id}")
        else:
            attrs_map = getattr(places, "attrs", None)
            if attrs_map is None or not hasattr(attrs_map, "get"):
                raise RuntimeError(
                    "world.places exposes neither patch API nor place records"
                )
            bucket = attrs_map.get(self.place_id)
            if bucket is None:
                attrs_map[self.place_id] = dict(self.attrs_patch)
            else:
                bucket.update(self.attrs_patch)

        world_db = getattr(world, "world_db", None)
        if world_db is not None:
            await world_db.update_place_attrs(self.place_id, self.attrs_patch)
