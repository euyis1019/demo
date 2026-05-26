"""HBM demo WorldStep — parallel LLM decisions within each place."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from agent_world.world.step import WorldStep, _extract_actions

log = logging.getLogger("agent_world.hbm_demo.world_step")


class HbmWorldStep(WorldStep):
    """Run co-located agents' ``perform_action_by_llm`` calls in parallel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tick_context: Optional[Dict[str, Any]] = None
        self._passive_ticks_batch: int = 0
        self._batch_tick_index: int = 0
        from agent_world.hbm_demo.features.f07_agent_control.batch_guard import (
            BatchGuardState,
        )

        self._batch_guard = BatchGuardState()

    def set_tick_context(
        self,
        turn_context: Optional[Dict[str, Any]],
        *,
        reset_l3_window: bool = False,
    ) -> None:
        from agent_world.hbm_demo.features.f07_agent_control.batch_guard import (
            BatchGuardState,
        )

        self._tick_context = dict(turn_context) if turn_context else None
        if reset_l3_window:
            self._passive_ticks_batch = 0
            self._batch_tick_index = 0
            self._batch_guard = BatchGuardState()

    def clear_tick_context(self) -> None:
        from agent_world.hbm_demo.features.f07_agent_control.batch_guard import (
            BatchGuardState,
        )

        self._tick_context = None
        self._passive_ticks_batch = 0
        self._batch_tick_index = 0
        self._batch_guard = BatchGuardState()

    @property
    def batch_guard(self) -> Any:
        return self._batch_guard

    async def run_one_tick(self) -> Dict[str, Any]:
        result = await super().run_one_tick()
        if self._tick_context is not None and self._tick_context.get("player_inject_tick") is None:
            self._batch_tick_index += 1
        return result

    def _pick_active(self, t: int) -> List[int]:
        from agent_world.hbm_demo.features.f07_agent_control.config import (
            is_f07_enabled,
            is_world_loop_enabled,
        )
        from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
            pick_active_ids,
            primary_active_ids,
        )
        from agent_world.hbm_demo.features.f07_agent_control.session_mirror import (
            bootstrap_mirror,
        )

        if not is_f07_enabled() or not self._tick_context:
            if is_world_loop_enabled():
                ctx = bootstrap_mirror()
                return pick_active_ids(ctx, self.world, t, batch_tick_index=999)
            return super()._pick_active(t)

        ctx = self._tick_context
        batch_tick_index = self._batch_tick_index
        inject_tick = ctx.get("player_inject_tick")
        if inject_tick is not None:
            batch_tick_index = max(0, int(t) - int(inject_tick))

        primary = set(primary_active_ids(ctx))
        active = pick_active_ids(
            ctx,
            self.world,
            t,
            passive_ticks_so_far=self._passive_ticks_batch,
            batch_tick_index=batch_tick_index,
        )
        passive_added = [aid for aid in active if aid not in primary]
        if passive_added:
            self._passive_ticks_batch += 1
        return active

    def _agent_place_id(self, agent_id: int) -> Optional[str]:
        """Place id for F15 links and player-facing F2F emission."""
        return self._location_of(int(agent_id))

    def _resolve_batch_llm_params(
        self,
        agent_id: int,
        turn_context: Dict[str, Any],
        llm: Dict[str, Any],
    ) -> Dict[str, Any]:
        from agent_world.hbm_demo.features.f07_agent_control.config import (
            is_experience_hardening,
        )
        from agent_world.hbm_demo.features.f07_agent_control.llm_params import (
            resolve_passive_llm_params,
        )

        if not is_experience_hardening():
            return llm
        phase = str(turn_context.get("phase", "Phase 1"))
        inject_ids = {int(x) for x in (turn_context.get("inject_agent_ids") or [])}
        if phase == "Phase 1" and agent_id not in inject_ids and agent_id in (2, 3):
            passive = resolve_passive_llm_params(phase)
            if passive:
                merged = dict(llm)
                merged.update(passive)
                return merged
        return llm

    async def _run_single_agent(self, agent_id: int, t: int) -> None:
        agent = self._resolve_agent(agent_id)
        if agent is None:
            return

        ctx = self._tick_context
        if ctx:
            agent._batch_turn_context = ctx  # noqa: SLF001
            agent._batch_guard_state = self._batch_guard  # noqa: SLF001
            llm = dict(ctx.get("llm_params") or {})
            llm = self._resolve_batch_llm_params(int(agent_id), ctx, llm)
            if llm:
                agent._batch_temperature = llm.get("temperature")  # noqa: SLF001
                agent._batch_max_tokens = llm.get("max_tokens")  # noqa: SLF001

        prompt_trace_id: Optional[str] = None
        try:
            decision = await self._decide(agent, agent_id, t)
        finally:
            prompt_trace_id = getattr(agent, "_prompt_trace_id", None)
            agent._prompt_trace_id = None  # noqa: SLF001
            if ctx:
                agent._batch_turn_context = None  # noqa: SLF001
                agent._batch_guard_state = None  # noqa: SLF001
                agent._batch_temperature = None  # noqa: SLF001
                agent._batch_max_tokens = None  # noqa: SLF001

        if decision is None or isinstance(decision, Exception):
            if isinstance(decision, Exception):
                log.warning("agent %s decide failed: %s", agent_id, decision)
            return

        for atype, akwargs in _extract_actions(decision):
            try:
                dispatch_result = await self.dispatcher.dispatch(
                    agent_id, atype, t, **(akwargs or {})
                )
                from agent_world.hbm_demo.features.f15_prompt_trace.linker import (
                    record_action_links,
                )

                await record_action_links(
                    self.world_db,
                    trace_id=prompt_trace_id,
                    agent_id=int(agent_id),
                    t=int(t),
                    action_type=atype,
                    action_kwargs=akwargs or {},
                    dispatch_result=dispatch_result,
                    place_id=self._agent_place_id(agent_id),
                )
                from agent_world.hbm_demo.features.f07_agent_control.conversation_control import (
                    mark_communication_action,
                )

                agent = self._resolve_agent(agent_id)
                if agent is not None:
                    mark_communication_action(
                        agent,
                        action_type=atype,
                        action_kwargs=akwargs or {},
                        dispatch_result=dispatch_result,
                        t=int(t),
                    )
                await self._handle_speak_to_local_f2f(
                    agent_id=agent_id,
                    action_type=atype,
                    action_kwargs=akwargs or {},
                    dispatch_result=dispatch_result,
                    t=t,
                )
                self._mark_rdc_if_sent(
                    agent_id=agent_id,
                    action_type=atype,
                    action_kwargs=akwargs or {},
                    dispatch_result=dispatch_result,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "dispatch(agent=%s, action=%s) failed: %s",
                    agent_id,
                    atype,
                    exc,
                )

    async def _handle_speak_to_local_f2f(
        self,
        *,
        agent_id: int,
        action_type: Any,
        action_kwargs: Dict[str, Any],
        dispatch_result: Any,
        t: int,
    ) -> None:
        from agent_world.hbm_demo.features.f07_agent_control.player_facing_f2f import (
            emit_player_facing_f2f,
            is_speak_to_local_action,
            should_emit_player_facing_f2f,
        )

        if not is_speak_to_local_action(action_type):
            return
        if not dispatch_result or not dispatch_result.get("success"):
            return

        recipients = dispatch_result.get("recipients")
        if isinstance(recipients, list) and len(recipients) > 0:
            self._batch_guard.mark_f2f(int(agent_id))
            return

        if not should_emit_player_facing_f2f(dispatch_result):
            return
        content = str(action_kwargs.get("content") or "").strip()
        if not content:
            return
        place_id = self._agent_place_id(agent_id)
        if not place_id or self.world_db is None:
            return
        try:
            await emit_player_facing_f2f(
                self.world_db,
                sender_id=int(agent_id),
                place_id=str(place_id),
                content=content,
                t=int(t),
            )
            self._batch_guard.mark_f2f(int(agent_id))
            log.debug(
                "F07-E0 player_facing_f2f agent=%s place=%s t=%s",
                agent_id,
                place_id,
                t,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "player_facing_f2f failed agent=%s: %s",
                agent_id,
                exc,
            )

    def _mark_rdc_if_sent(
        self,
        *,
        agent_id: int,
        action_type: Any,
        action_kwargs: Dict[str, Any],
        dispatch_result: Any,
    ) -> None:
        from agent_world.hbm_demo.features.f07_agent_control.config import (
            is_experience_hardening,
        )
        from agent_world.hbm_demo.features.f07_agent_control.player_facing_f2f import (
            is_speak_to_local_action,
        )

        if not is_experience_hardening():
            return
        if is_speak_to_local_action(action_type):
            return
        name = str(
            getattr(action_type, "value", None)
            or getattr(action_type, "name", None)
            or action_type
            or ""
        )
        if name.lower().replace("-", "_") != "send_message":
            return
        if not dispatch_result or not dispatch_result.get("success"):
            return
        target = action_kwargs.get("target")
        if target is None:
            return
        self._batch_guard.mark_rdc(int(agent_id), int(target))

    async def _run_place(
        self, place_id: str, agent_ids: List[int], t: int
    ) -> None:
        if not agent_ids:
            return
        if len(agent_ids) == 1:
            await self._run_single_agent(agent_ids[0], t)
            return

        results = await asyncio.gather(
            *[self._run_single_agent(aid, t) for aid in agent_ids],
            return_exceptions=True,
        )
        for aid, result in zip(agent_ids, results):
            if isinstance(result, Exception):
                log.error(
                    "parallel _run_place(%s) agent=%s raised: %s",
                    place_id,
                    aid,
                    result,
                )
