"""IPC handler registration for HBM demo Runner (Phase 1+)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict

from agent_world.hbm_demo.core.runner import broadcast_helper
from agent_world.hbm_demo.features.f01_session.world_reset import reset_world_runtime
from agent_world.hbm_demo.shared.env_status import write_env_status
from agent_world.ipc.commands import CommandType
from agent_world.script.loader import ScriptLoader

log = logging.getLogger("agent_world.hbm_demo.ipc")


def wire_handlers(
    ipc_server: Any,
    *,
    world_db: Any,
    world_state: Any,
    place_store: Any,
    relation_graph: Any,
    capability_table: Any,
    connectivity: Any,
    script_engine: Any,
    world_step: Any,
    agents: Any,
    scenario: Dict[str, Any],
    segment_store: Any,
    sim_dir: str | Path,
    get_current_tick: Callable[[], int],
) -> None:
    """Register LIST_PLACES, MOVE_AGENT, full INJECT, RESET_WORLD, and CLOSE_ENV."""

    sim_dir_str = str(Path(sim_dir).resolve())

    async def handle_inject_script_event(payload: Dict[str, Any]) -> Dict[str, Any]:
        start_tick = int(world_state.clock.t)
        log.info(
            "INJECT_SCRIPT_EVENT keys=%s start_tick=%s",
            list(payload.keys()),
            start_tick,
        )

        bc = payload.get("broadcast")
        if bc:
            await broadcast_helper.broadcast_place(
                world_db,
                place_store,
                str(bc["place_id"]),
                str(bc["message"]),
                t=int(world_state.clock.t),
            )

        events = list(payload.get("events") or [])
        if payload.get("event"):
            events = [payload["event"]]

        from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
            clear_player_memory_for_agents,
            extract_inject_agent_ids,
            is_f07_enabled,
        )

        if events and is_f07_enabled():
            inject_ids = extract_inject_agent_ids(events)
            if inject_ids:
                clear_player_memory_for_agents(agents, inject_ids)

        if events:
            result = ScriptLoader.load_dict(
                {"events": events},
                existing_ids=script_engine.loaded_event_ids,
            )
            for ev in result.events:
                script_engine.events_by_id[ev.id] = ev
                script_engine.loaded_event_ids.add(ev.id)

        n = int(payload.get("tick_count", 6))
        tick_loops = max(3, min(n, 8))

        for _ in range(tick_loops):
            await world_step.run_one_tick()
            write_env_status(sim_dir_str, get_current_tick())

        end_tick = int(world_state.clock.t)
        return {
            "start_tick": start_tick,
            "end_tick": end_tick,
            "world_t": end_tick,
        }

    async def handle_list_places(payload: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        places = []
        for rec in place_store.all_places():
            places.append(
                {
                    "place_id": rec.place_id,
                    "parent_id": rec.parent_id,
                    "place_type": rec.place_type,
                    "capacity": rec.capacity,
                    "attrs": dict(rec.attrs),
                }
            )
        return {"places": places, "agent_locations": dict(place_store.L)}

    async def handle_move_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            agent_id = int(payload["agent_id"])
            new_place = str(payload["place_id"])
        except (KeyError, TypeError, ValueError) as exc:
            return {"error": f"bad payload: {exc}"}
        old_place = place_store.L_t(agent_id) or ""
        try:
            await place_store.move(
                agent_id,
                new_place,
                world=world_state,
                t=world_state.t,
            )
            return {"old_place": old_place, "new_place": new_place}
        except Exception as exc:  # noqa: BLE001
            log.warning("MOVE_AGENT failed agent=%s err=%s", agent_id, exc)
            return {
                "old_place": old_place,
                "new_place": new_place,
                "error": str(exc),
            }

    async def handle_close_env(payload: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        ipc_server.stop()
        return {}

    async def handle_reset_world(payload: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        end_tick = await reset_world_runtime(
            world_db=world_db,
            world_state=world_state,
            place_store=place_store,
            relation_graph=relation_graph,
            capability_table=capability_table,
            connectivity=connectivity,
            script_engine=script_engine,
            agents=agents,
            scenario=scenario,
            clock=world_state.clock,
            segment_store=segment_store,
            sim_dir=sim_dir_str,
        )
        return {"end_tick": end_tick, "world_t": end_tick}

    ipc_server.register_handler(
        CommandType.INJECT_SCRIPT_EVENT,
        handle_inject_script_event,
    )
    ipc_server.register_handler(CommandType.LIST_PLACES, handle_list_places)
    ipc_server.register_handler(CommandType.MOVE_AGENT, handle_move_agent)
    ipc_server.register_handler(CommandType.RESET_WORLD, handle_reset_world)
    ipc_server.register_handler(CommandType.CLOSE_ENV, handle_close_env)
