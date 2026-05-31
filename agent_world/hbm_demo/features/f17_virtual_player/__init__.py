"""F17 — Virtual Player Entity (canonical virtual-player feature, agent 0)."""

from agent_world.hbm_demo.features.f17_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)
from agent_world.hbm_demo.features.f17_virtual_player.player_entity import (
    is_virtual_player_agent,
)
from agent_world.hbm_demo.features.f17_virtual_player.player_f2f import (
    apply_player_f2f_payload,
    build_player_f2f_payload,
)

__all__ = [
    "apply_player_f2f_payload",
    "build_player_f2f_payload",
    "is_f08_enabled",
    "is_virtual_player_agent",
    "player_agent_id",
]
