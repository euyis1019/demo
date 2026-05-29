"""F12 shared constants — HBM demo room grid and agent roster."""

from __future__ import annotations

from agent_world.hbm_demo.shared.routing_events import (
    PLACE_MUTATION_HINT,
    ROUTING_WORLD_EVENT_CONTENT,
)

HBM_ROOM_PLACES: tuple[str, ...] = (
    "nvidia_reception",
    "jensen_private_room",
    "negotiation_room",
    "openai_hq",
)

HBM_AGENT_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)

__all__ = [
    "HBM_AGENT_IDS",
    "HBM_ROOM_PLACES",
    "PLACE_MUTATION_HINT",
    "ROUTING_WORLD_EVENT_CONTENT",
]
