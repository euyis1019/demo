"""F12 — world sync persistence hooks + Flask read-model delta (Phase 2)."""

from __future__ import annotations

__all__ = [
    "build_world_delta",
    "build_completed_payload",
    "empty_delta",
    "get_world_snapshot",
]


def __getattr__(name: str):  # noqa: ANN001
    if name in ("build_world_delta", "build_completed_payload", "empty_delta"):
        from agent_world.hbm_demo.features.f12_world_sync import delta as _delta

        return getattr(_delta, name)
    if name == "get_world_snapshot":
        from agent_world.hbm_demo.features.f12_world_sync.handler import (
            get_world_snapshot as _fn,
        )

        return _fn
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
