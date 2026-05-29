"""IPC handler registration for HBM demo Runner (Phase 1+)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from agent_world.hbm_demo.core.runner.world_loop import WorldLoopOrchestrator
from agent_world.hbm_demo.core.runner.integration import abcs
from agent_world.hbm_demo.core.runner.integration import virtual_player
from agent_world.hbm_demo.features.f01_session.world_reset import (
    purge_prompt_traces,
    reset_world_runtime,
)
from agent_world.hbm_demo.core.runner.integration import abcs
from agent_world.hbm_demo.shared.env_status import write_env_status
from agent_world.ipc.commands import CommandType

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
    orchestrator: Optional[WorldLoopOrchestrator] = None,
) -> None:
    """Register LIST_PLACES, MOVE_AGENT, inject/enqueue, RESET_WORLD, and CLOSE_ENV."""

    sim_dir_str = str(Path(sim_dir).resolve())

    async def _legacy_inject_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
        """v1 fallback when world loop disabled."""
        start_tick = int(world_state.clock.t)
        from agent_world.hbm_demo.core.runner import broadcast_helper
        from agent_world.script.loader import ScriptLoader

        bc = payload.get("broadcast")
        player_f2f = payload.get("player_f2f")
        if player_f2f:
            await virtual_player.apply_player_f2f_payload(
                world_db,
                player_f2f,
                t=int(world_state.clock.t),
            )
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

        turn_context = payload.get("turn_context") or {}
        if hasattr(world_step, "set_tick_context"):
            world_step.set_tick_context(
                turn_context if abcs.is_f07_enabled() else None,
                reset_l3_window=True,
            )

        if events and abcs.is_f07_enabled():
            inject_ids = abcs.extract_inject_agent_ids(events)
            if inject_ids:
                abcs.clear_player_memory_for_agents(agents, inject_ids)
            if turn_context:
                abcs.notify_non_inject_active_agents(
                    script_engine,
                    turn_context,
                    inject_ids,
                )

        if events:
            result = ScriptLoader.load_dict(
                {"events": events},
                existing_ids=script_engine.loaded_event_ids,
            )
            loaded = list(result.events)
            for ev in loaded:
                script_engine.events_by_id[ev.id] = ev
                script_engine.loaded_event_ids.add(ev.id)
            if loaded:
                await script_engine.apply(
                    loaded, world_state, int(world_state.clock.t)
                )

        n = int(payload.get("tick_count", 6))
        tick_loops = abcs.resolve_inject_tick_loops(n)
        try:
            for _ in range(tick_loops):
                await world_step.run_one_tick()
                write_env_status(sim_dir_str, get_current_tick())
        finally:
            if hasattr(world_step, "clear_tick_context"):
                world_step.clear_tick_context()

        end_tick = int(world_state.clock.t)
        return {
            "start_tick": start_tick,
            "end_tick": end_tick,
            "world_t": end_tick,
        }

    async def handle_inject_script_event(payload: Dict[str, Any]) -> Dict[str, Any]:
        log.info(
            "INJECT_SCRIPT_EVENT keys=%s tick=%s loop=%s",
            list(payload.keys()),
            get_current_tick(),
            abcs.is_world_loop_enabled(),
        )
        if orchestrator is not None and orchestrator.enabled:
            return orchestrator.enqueue_script_event(payload)
        return await _legacy_inject_batch(payload)

    async def handle_enqueue_player_input(payload: Dict[str, Any]) -> Dict[str, Any]:
        if orchestrator is None or not orchestrator.enabled:
            return await _legacy_inject_batch(payload)
        return orchestrator.enqueue_player_input(payload)

    async def handle_update_session_mirror(payload: Dict[str, Any]) -> Dict[str, Any]:
        if orchestrator is None or not orchestrator.enabled:
            return {"ok": False, "reason": "world_loop_disabled"}
        return orchestrator.update_session_mirror(payload)

    async def handle_get_loop_status(payload: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        if orchestrator is None or not orchestrator.enabled:
            return {
                "loop_running": False,
                "loop_state": "disabled",
                "current_tick": int(get_current_tick()),
                "world_t": int(get_current_tick()),
            }
        return orchestrator.get_loop_status()

    async def handle_pause_loop(payload: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        if orchestrator is None or not orchestrator.enabled:
            return {"ok": False, "reason": "world_loop_disabled"}
        return orchestrator.pause()

    async def handle_resume_loop(payload: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        if orchestrator is None or not orchestrator.enabled:
            return {"ok": False, "reason": "world_loop_disabled"}
        return orchestrator.resume()

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
                source="ipc_move",
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
        if orchestrator is not None:
            await orchestrator.stop()
        ipc_server.stop()
        return {}

    async def handle_reset_world(payload: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        if orchestrator is not None and orchestrator.enabled:
            await orchestrator.pause_for_reset()
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
        async with world_db._write_lock:
            purge_prompt_traces(world_db)
        if hasattr(world_step, "clear_tick_context"):
            world_step.clear_tick_context()
        if orchestrator is not None:
            orchestrator.clear_session_state()
            if orchestrator.enabled:
                orchestrator.update_session_mirror({})
                orchestrator.mark_hold_paused_after_reset()
                write_env_status(
                    sim_dir_str,
                    end_tick,
                    status="running",
                    loop_running=True,
                    loop_state="paused",
                    last_activity_t=0,
                    queue_depth=0,
                    paused_at_tick=end_tick,
                    paused_at_iso=None,
                    tick_interval_sec=orchestrator.get_loop_status().get(
                        "tick_interval_sec"
                    ),
                )
        return {"end_tick": end_tick, "world_t": end_tick}

    ipc_server.register_handler(
        CommandType.INJECT_SCRIPT_EVENT,
        handle_inject_script_event,
    )
    ipc_server.register_handler(
        CommandType.ENQUEUE_PLAYER_INPUT,
        handle_enqueue_player_input,
    )
    ipc_server.register_handler(
        CommandType.UPDATE_SESSION_MIRROR,
        handle_update_session_mirror,
    )
    ipc_server.register_handler(
        CommandType.GET_LOOP_STATUS,
        handle_get_loop_status,
    )
    ipc_server.register_handler(CommandType.PAUSE_LOOP, handle_pause_loop)
    ipc_server.register_handler(CommandType.RESUME_LOOP, handle_resume_loop)
    ipc_server.register_handler(CommandType.LIST_PLACES, handle_list_places)
    ipc_server.register_handler(CommandType.MOVE_AGENT, handle_move_agent)
    ipc_server.register_handler(CommandType.RESET_WORLD, handle_reset_world)
    ipc_server.register_handler(CommandType.CLOSE_ENV, handle_close_env)
