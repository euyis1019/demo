"""HBM v2 WorldLoopOrchestrator — resident tick loop (dev_logs/31 §四, §8.3)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from agent_world.hbm_demo.core.runner import broadcast_helper
from agent_world.hbm_demo.core.runner.player_input_queue import (
    PlayerInputItem,
    PlayerInputQueue,
    ScriptQueueItem,
)
from agent_world.hbm_demo.features.f07_agent_control.config import (
    is_f07_enabled,
    is_world_loop_enabled,
    pause_drains_queue,
    player_input_max_depth,
    world_loop_max_ticks,
    world_loop_tick_interval,
)
from agent_world.hbm_demo.features.f07_agent_control.inject_batch import (
    notify_non_inject_active_agents,
)
from agent_world.hbm_demo.features.f07_agent_control.session_mirror import (
    bootstrap_mirror,
    merge_mirror_update,
    mirror_from_payload,
)
from agent_world.hbm_demo.features.f07_agent_control.turn_context import (
    clear_player_memory_for_agents,
    extract_inject_agent_ids,
)
from agent_world.hbm_demo.shared.env_status import write_env_status
from agent_world.script.loader import ScriptLoader

log = logging.getLogger("agent_world.hbm_demo.world_loop")


class SessionMirrorState:
    """Runner-side session snapshot (Flask is authoritative)."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = bootstrap_mirror()

    def latest(self) -> Dict[str, Any]:
        return dict(self._data)

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        self._data = merge_mirror_update(self._data, patch)
        return dict(self._data)

    def replace(self, mirror: Dict[str, Any]) -> Dict[str, Any]:
        self._data = dict(mirror)
        return dict(self._data)

    def reset(self) -> None:
        self._data = bootstrap_mirror()


class WorldLoopOrchestrator:
    """Resident asyncio loop: drain queue → run_one_tick → sleep (beat A)."""

    def __init__(
        self,
        *,
        world_db: Any,
        world_state: Any,
        place_store: Any,
        script_engine: Any,
        world_step: Any,
        agents: Any,
        sim_dir: str,
        get_current_tick: Callable[[], int],
    ) -> None:
        self._world_db = world_db
        self._world_state = world_state
        self._place_store = place_store
        self._script_engine = script_engine
        self._world_step = world_step
        self._agents = agents
        self._sim_dir = str(sim_dir)
        self._get_current_tick = get_current_tick

        self._queue = PlayerInputQueue(max_depth=player_input_max_depth())
        self._mirror = SessionMirrorState()
        self._running = False
        self._loop_task: Optional[asyncio.Task[None]] = None
        self._last_activity_t: int = 0
        self._last_player_inject_tick: Optional[int] = None
        self._ticks_run: int = 0
        self._loop_state: str = "stopped"
        self._paused_at_tick: Optional[int] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._cycle_lock = asyncio.Lock()
        self._hold_paused_after_reset = False

    @property
    def enabled(self) -> bool:
        return is_world_loop_enabled()

    async def start(self) -> None:
        if not self.enabled:
            log.info("world loop disabled in turn_control.yaml")
            return
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._running = True
        self._loop_state = "running"
        self._paused_at_tick = None
        self._pause_event.set()
        self._loop_task = asyncio.create_task(self._loop(), name="hbm-world-loop")
        log.info("WorldLoopOrchestrator started interval=%ss", world_loop_tick_interval())

    async def stop(self) -> None:
        self._running = False
        self._pause_event.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        self._loop_state = "stopped"
        self._write_status(loop_running=False)

    def reset_runtime(self) -> None:
        self.clear_session_state()
        self._loop_state = "running"
        self._paused_at_tick = None
        self._hold_paused_after_reset = False
        self._pause_event.set()

    def clear_session_state(self) -> None:
        """Clear queue + mirror without changing pause/running flags."""
        self._queue.clear()
        self._mirror.reset()
        self._last_activity_t = 0
        self._last_player_inject_tick = None
        self._ticks_run = 0

    async def pause_for_reset(self) -> None:
        """Block the resident loop for RESET_WORLD (avoid tick/trace races)."""
        if not self.enabled or not self._running:
            return
        self._loop_state = "paused"
        self._paused_at_tick = int(self._get_current_tick())
        self._pause_event.clear()
        async with self._cycle_lock:
            pass
        self._write_status(loop_running=bool(self._running))

    def mark_hold_paused_after_reset(self) -> None:
        self._hold_paused_after_reset = True
        self._loop_state = "paused"
        self._paused_at_tick = int(self._get_current_tick())
        self._pause_event.clear()

    def resume_after_reset_if_held(self) -> None:
        if not self._hold_paused_after_reset:
            return
        self._hold_paused_after_reset = False
        if self._loop_state == "paused":
            self.resume()

    def pause(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "world_loop_disabled"}
        tick = int(self._get_current_tick())
        if self._loop_state == "paused":
            return self._pause_payload(already=True)
        self._loop_state = "paused"
        self._paused_at_tick = tick
        self._pause_event.clear()
        self._write_status(loop_running=bool(self._running))
        log.info("world loop paused at tick=%s", tick)
        return self._pause_payload()

    def resume(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "world_loop_disabled"}
        tick = int(self._get_current_tick())
        if self._loop_state != "paused":
            return self._resume_payload(already=True)
        self._loop_state = "running"
        self._paused_at_tick = None
        self._pause_event.set()
        self._write_status(loop_running=bool(self._running))
        log.info("world loop resumed at tick=%s", tick)
        return self._resume_payload()

    def _pause_payload(self, *, already: bool = False) -> Dict[str, Any]:
        tick = int(self._get_current_tick())
        out = {
            "ok": True,
            "loop_state": "paused",
            "paused_at_tick": int(self._paused_at_tick if self._paused_at_tick is not None else tick),
            "world_t": tick,
            "current_tick": tick,
        }
        if already:
            out["already_paused"] = True
        return out

    def _resume_payload(self, *, already: bool = False) -> Dict[str, Any]:
        tick = int(self._get_current_tick())
        out = {
            "ok": True,
            "loop_state": "running",
            "world_t": tick,
            "current_tick": tick,
        }
        if already:
            out["already_running"] = True
        return out

    def enqueue_player_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.resume_after_reset_if_held()
        events = list(payload.get("events") or [])
        if payload.get("event"):
            events = [payload["event"]]
        turn_context = dict(payload.get("turn_context") or {})
        broadcast = payload.get("broadcast")
        player_f2f = payload.get("player_f2f")
        item = PlayerInputItem(
            events=events,
            turn_context=turn_context,
            broadcast=broadcast if isinstance(broadcast, dict) else None,
            player_f2f=player_f2f if isinstance(player_f2f, dict) else None,
        )
        if not self._queue.enqueue_player(item):
            return {"accepted": False, "reason": "queue_full"}
        return {
            "accepted": True,
            "enqueue_tick": int(self._get_current_tick()),
            **self._queue.stats(),
        }

    def enqueue_script_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        events = list(payload.get("events") or [])
        if payload.get("event"):
            events = [payload["event"]]
        broadcast = payload.get("broadcast")
        item = ScriptQueueItem(
            events=events,
            broadcast=broadcast if isinstance(broadcast, dict) else None,
        )
        if not self._queue.enqueue_script(item):
            return {"accepted": False, "reason": "queue_full"}
        return {
            "accepted": True,
            "enqueue_tick": int(self._get_current_tick()),
            **self._queue.stats(),
        }

    def update_session_mirror(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prev = self._mirror.latest()
        prev_start = prev.get("start_tick")
        mirror = mirror_from_payload(payload) if payload else bootstrap_mirror()
        if payload.get("turn_context"):
            mirror = merge_mirror_update(prev, payload["turn_context"])
        elif payload:
            mirror = merge_mirror_update(prev, payload)
        updated = self._mirror.replace(mirror)
        new_start = updated.get("start_tick")
        if new_start is not None and new_start != prev_start:
            self._last_player_inject_tick = None
            if hasattr(self._world_step, "set_tick_context"):
                self._world_step.set_tick_context(updated, reset_l3_window=True)
        return {"ok": True, "mirror": updated}

    def get_loop_status(self) -> Dict[str, Any]:
        tick = int(self._get_current_tick())
        stats = self._queue.stats()
        loop_state = self._loop_state if self._running else "stopped"
        return {
            "loop_running": bool(self._running and self.enabled and loop_state == "running"),
            "loop_state": loop_state,
            "current_tick": tick,
            "world_t": tick,
            "tick_interval_sec": world_loop_tick_interval(),
            "last_activity_t": int(self._last_activity_t),
            "last_player_inject_tick": self._last_player_inject_tick,
            "paused_at_tick": self._paused_at_tick,
            "ticks_run": int(self._ticks_run),
            **stats,
        }

    async def _loop(self) -> None:
        interval = world_loop_tick_interval()
        max_ticks = world_loop_max_ticks()
        try:
            while self._running:
                await self._pause_event.wait()
                if not self._running:
                    break
                if self._ticks_run >= max_ticks:
                    log.warning("world loop hit max_ticks=%s — stopping", max_ticks)
                    break
                await self._run_one_cycle()
                self._ticks_run += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("world loop crashed: %s", exc)
        finally:
            self._running = False
            self._loop_state = "stopped"
            self._write_status(loop_running=False)

    async def _run_one_cycle(self) -> None:
        async with self._cycle_lock:
            tick_before = int(self._get_current_tick())
            inject_turn_ctx = await self._drain_queue()
            mirror = self._mirror.latest()
            if inject_turn_ctx is not None:
                mirror = dict(inject_turn_ctx)
            elif self._last_player_inject_tick is not None:
                mirror["player_inject_tick"] = int(self._last_player_inject_tick)
            if hasattr(self._world_step, "set_tick_context"):
                reset_window = inject_turn_ctx is not None
                self._world_step.set_tick_context(
                    mirror if is_f07_enabled() else None,
                    reset_l3_window=reset_window,
                )
            await self._world_step.run_one_tick()
            tick_after = int(self._get_current_tick())
            if tick_after > tick_before:
                self._last_activity_t = tick_after
            self._write_status(loop_running=True)

    async def _drain_queue(self) -> Optional[Dict[str, Any]]:
        if self._loop_state == "paused" and not pause_drains_queue():
            return None

        players, scripts = self._queue.drain_for_tick()
        if not players and not scripts:
            return None

        frozen_turn_context: Optional[Dict[str, Any]] = None

        for item in players:
            if item.player_f2f:
                from agent_world.hbm_demo.features.f08_virtual_player.player_f2f import (
                    apply_player_f2f_payload,
                )

                await apply_player_f2f_payload(
                    self._world_db,
                    item.player_f2f,
                    t=int(self._world_state.clock.t),
                )
            if item.broadcast:
                await broadcast_helper.broadcast_place(
                    self._world_db,
                    self._place_store,
                    str(item.broadcast["place_id"]),
                    str(item.broadcast["message"]),
                    t=int(self._world_state.clock.t),
                )
            if item.events and is_f07_enabled():
                inject_ids = extract_inject_agent_ids(item.events)
                if inject_ids:
                    clear_player_memory_for_agents(self._agents, inject_ids)
                if item.turn_context:
                    notify_non_inject_active_agents(
                        self._script_engine,
                        item.turn_context,
                        inject_ids,
                    )
            await self._load_events(item.events)
            if item.turn_context:
                frozen_turn_context = dict(item.turn_context)
                self._last_player_inject_tick = int(self._world_state.clock.t)
                frozen_turn_context["player_inject_tick"] = self._last_player_inject_tick

        for item in scripts:
            if item.broadcast:
                await broadcast_helper.broadcast_place(
                    self._world_db,
                    self._place_store,
                    str(item.broadcast["place_id"]),
                    str(item.broadcast["message"]),
                    t=int(self._world_state.clock.t),
                )
            await self._load_events(item.events)

        return frozen_turn_context

    async def _load_events(self, events: List[Dict[str, Any]]) -> None:
        if not events:
            return
        result = ScriptLoader.load_dict(
            {"events": events},
            existing_ids=self._script_engine.loaded_event_ids,
        )
        loaded = list(result.events)
        for ev in loaded:
            self._script_engine.events_by_id[ev.id] = ev
            self._script_engine.loaded_event_ids.add(ev.id)
        if not loaded:
            return
        t = int(self._get_current_tick())
        await self._script_engine.apply(loaded, self._world_state, t)
        log.debug(
            "world loop applied %d script events at t=%s ids=%s",
            len(loaded),
            t,
            [ev.id for ev in loaded],
        )

    def _write_status(self, *, loop_running: bool) -> None:
        paused_iso: Optional[str] = None
        if self._loop_state == "paused" and self._paused_at_tick is not None:
            paused_iso = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        write_env_status(
            self._sim_dir,
            self._get_current_tick(),
            status="running",
            loop_running=loop_running,
            loop_state=self._loop_state if self._running else "stopped",
            last_activity_t=int(self._last_activity_t),
            queue_depth=int(self._queue.depth()),
            paused_at_tick=self._paused_at_tick,
            paused_at_iso=paused_iso,
            tick_interval_sec=world_loop_tick_interval(),
        )


__all__ = ["SessionMirrorState", "WorldLoopOrchestrator"]
