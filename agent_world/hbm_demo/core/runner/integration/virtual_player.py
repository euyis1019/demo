"""Runner ↔ F08V virtual player bridge."""

from agent_world.hbm_demo.features.f17_virtual_player.config import (
    is_f08_enabled,
    player_agent_id,
)
from agent_world.hbm_demo.features.f17_virtual_player.player_f2f import (
    apply_player_f2f_payload,
)
from agent_world.hbm_demo.features.f17_virtual_player.player_actions import (
    apply_player_grp_payload,
    apply_player_rdc_payload,
)

__all__ = [
    "apply_player_f2f_payload",
    "apply_player_rdc_payload",
    "apply_player_grp_payload",
    "is_f08_enabled",
    "player_agent_id",
]
