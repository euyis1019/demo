"""Reset in-memory + SQLite world state to scenario initial (HBM demo restart)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TYPE_CHECKING

from agent_world.hbm_demo.shared.env_status import write_env_status
from agent_world.hbm_demo.core.runner.hbm_agent import HbmAgent
from agent_world.hbm_demo.core.runner.seed import seed_world

if TYPE_CHECKING:
    from agent_world.memory.segment import SegmentStore
    from agent_world.persistence.world_db import WorldDB
    from agent_world.script.engine import ScriptEngine
    from agent_world.world.clock import Clock
    from agent_world.world.connectivity import ConnectivityResolver
    from agent_world.world.place_store import PlaceStore
    from agent_world.world.relation_graph import RelationGraph
    from agent_world.world.state import WorldState

log = logging.getLogger("agent_world.hbm_demo.world_reset")

_VOLATILE_TABLES = (
    "overhear",
    "direct_message",
    "group_message",
    "script_event_log",
    "agent_location_log",
    "agent_state_log",
)


async def reset_world_runtime(
    *,
    world_db: WorldDB,
    world_state: WorldState,
    place_store: PlaceStore,
    relation_graph: RelationGraph,
    capability_table: Any,
    connectivity: ConnectivityResolver,
    script_engine: ScriptEngine,
    agents: List[HbmAgent],
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

    clock.t = 0

    script_engine.events_by_id.clear()
    script_engine.loaded_event_ids.clear()
    script_engine.applied_events.clear()

    for agent in agents:
        agent.player_memory.clear()
        segment_store.clear(agent.agent_id)

    await seed_world(
        world_db,
        capability_table,
        relation_graph,
        connectivity,
        scenario,
    )

    place_store.load_from_db(world_db)
    relation_graph.load_from_db(world_db)

    write_env_status(sim_dir, 0, status="running")
    log.info(
        "world reset complete agents=%d tick=0 sim_dir=%s",
        len(agents),
        sim_dir,
    )
    return 0
