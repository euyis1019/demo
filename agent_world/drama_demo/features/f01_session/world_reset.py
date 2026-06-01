"""Reset in-memory + SQLite world state to scenario initial (HBM demo restart)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TYPE_CHECKING

from agent_world.drama_demo.shared.env_status import write_env_status
from agent_world.drama_demo.core.runner.drama_agent import DramaAgent
from agent_world.drama_demo.core.runner.seed import seed_world

if TYPE_CHECKING:
    from agent_world.memory.segment import SegmentStore
    from agent_world.persistence.world_db import WorldDB
    from agent_world.script.engine import ScriptEngine
    from agent_world.world.clock import Clock
    from agent_world.world.connectivity import ConnectivityResolver
    from agent_world.world.place_store import PlaceStore
    from agent_world.world.relation_graph import RelationGraph
    from agent_world.world.state import WorldState

log = logging.getLogger("agent_world.drama_demo.world_reset")

# Runtime message / trace / log tables cleared on every RESET_WORLD.
_VOLATILE_TABLES = (
    "overhear",
    "direct_message",
    "group_message",
    "group_event",
    "group_member",
    "script_event_log",
    "agent_location_log",
    "agent_state_log",
    "agent_action_trace_link",
    "agent_llm_trace",
    "story_advance_log",
    "capability",
)


def _restore_agents_from_scenario(
    agents: List[DramaAgent],
    scenario: Dict[str, Any],
) -> None:
    """Reset in-memory agent fields that are not stored in volatile SQL tables."""
    cfg_by_id = {int(a["agent_id"]): a for a in scenario.get("agents", [])}
    for agent in agents:
        cfg = cfg_by_id.get(int(agent.agent_id), {})
        agent.soul = str(cfg.get("soul", agent.soul) or "").strip()
        agent.long_term_goal = str(
            cfg.get("long_term_goal", agent.long_term_goal) or ""
        ).strip()
        agent.current_state = str(cfg.get("current_state", "") or "").strip()
        agent.short_term_goal = str(cfg.get("short_term_goal", "") or "").strip()
        agent.current_state_set_at = 0
        agent.last_message_seen_at = -1
        agent.player_memory.clear()
        agent._pending_rdc_out = {}  # noqa: SLF001
        agent._inject_responded = False  # noqa: SLF001
        if hasattr(agent, "_batch_turn_context"):
            agent._batch_turn_context = None  # noqa: SLF001
        if hasattr(agent, "_batch_temperature"):
            agent._batch_temperature = None  # noqa: SLF001
        if hasattr(agent, "_batch_max_tokens"):
            agent._batch_max_tokens = None  # noqa: SLF001
        if hasattr(agent, "_prompt_trace_id"):
            agent._prompt_trace_id = None  # noqa: SLF001


async def reset_world_runtime(
    *,
    world_db: WorldDB,
    world_state: WorldState,
    place_store: PlaceStore,
    relation_graph: RelationGraph,
    capability_table: Any,
    connectivity: ConnectivityResolver,
    script_engine: ScriptEngine,
    agents: List[DramaAgent],
    scenario: Dict[str, Any],
    clock: Clock,
    segment_store: SegmentStore,
    sim_dir: str,
) -> int:
    """Clear messages/ticks, restore agent locations & relations from YAML."""
    async with world_db._write_lock:
        for table in _VOLATILE_TABLES:
            world_db._exec(f"DELETE FROM {table}")
        world_db._exec("DELETE FROM relation")

    # Drop stale in-memory relation/capability before re-seed.  Otherwise
    # grant/add idempotently skip while DB rows were just deleted, and the
    # load_from_db below would wipe connectivity entirely (all RDC φ fail).
    relation_graph.load_from_db(world_db)
    if hasattr(capability_table, "load_from_db"):
        capability_table.load_from_db(world_db)

    clock.t = 0

    script_engine.events_by_id.clear()
    script_engine.loaded_event_ids.clear()
    script_engine.applied_events.clear()

    for agent in agents:
        segment_store.clear(agent.agent_id)

    _restore_agents_from_scenario(agents, scenario)

    await seed_world(
        world_db,
        capability_table,
        relation_graph,
        connectivity,
        scenario,
    )

    place_store.load_from_db(world_db)
    relation_graph.load_from_db(world_db)
    if hasattr(capability_table, "load_from_db"):
        capability_table.load_from_db(world_db)

    purge_prompt_traces(world_db)

    write_env_status(sim_dir, 0, status="running")
    log.info(
        "world reset complete agents=%d tick=0 sim_dir=%s",
        len(agents),
        sim_dir,
    )
    return 0


def purge_prompt_traces(world_db: WorldDB) -> None:
    """Remove F15 audit rows (also called after RESET_WORLD under write lock)."""
    world_db._exec("DELETE FROM agent_action_trace_link")
    world_db._exec("DELETE FROM agent_llm_trace")


__all__ = ["reset_world_runtime", "_VOLATILE_TABLES", "purge_prompt_traces"]
