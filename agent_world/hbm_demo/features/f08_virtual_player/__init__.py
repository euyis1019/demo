"""F08 — Virtual player entity (agent 0, no LLM tick)."""

from agent_world.hbm_demo.features.f08_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)
from agent_world.hbm_demo.features.f08_virtual_player.player_entity import (
    PLAYER_AGENT_ID,
    sync_player_place_on_routing,
    target_place_for_phase,
)
from agent_world.hbm_demo.features.f08_virtual_player.player_f2f import (
    apply_player_f2f_payload,
    build_player_f2f_payload,
    f2f_recipient_for_phase,
)

__all__ = [
    "PLAYER_AGENT_ID",
    "apply_player_f2f_payload",
    "build_player_f2f_payload",
    "f2f_recipient_for_phase",
    "is_f08_enabled",
    "player_agent_id",
    "sync_player_place_on_routing",
    "target_place_for_phase",
]
