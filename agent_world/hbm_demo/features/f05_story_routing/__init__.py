"""F05 — Phase routing nodes A/B/C/D and inject payload assembly."""

from agent_world.hbm_demo.features.f05_story_routing.routing import (
    PHASE_INJECT_AGENTS,
    apply_routing,
    build_dialogue_event,
    build_inject_payload,
    classify_turn25_intent,
    format_player_dialogue,
    inject_agent_ids_for_phase,
    node_a_applies,
    node_b_applies,
    node_c_applies,
    resolve_ending_id,
)

__all__ = [
    "PHASE_INJECT_AGENTS",
    "apply_routing",
    "build_dialogue_event",
    "build_inject_payload",
    "classify_turn25_intent",
    "format_player_dialogue",
    "inject_agent_ids_for_phase",
    "node_a_applies",
    "node_b_applies",
    "node_c_applies",
    "resolve_ending_id",
]
