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

    def set_tick_context(self, turn_context: Optional[Dict[str, Any]]) -> None:
        self._tick_context = dict(turn_context) if turn_context else None
        self._passive_ticks_batch = 0

    def clear_tick_context(self) -> None:
        self._tick_context = None
        self._passive_ticks_batch = 0

    def _pick_active(self, t: int) -> List[int]:
        from agent_world.hbm_demo.features.f07_agent_control.config import (
            is_f07_enabled,
        )
        from agent_world.hbm_demo.features.f07_agent_control.pick_active import (
            pick_active_ids,
            primary_active_ids,
        )

        if not is_f07_enabled() or not self._tick_context:
            return super()._pick_active(t)

        primary = set(primary_active_ids(self._tick_context))
        active = pick_active_ids(
            self._tick_context,
            self.world,
            t,
            passive_ticks_so_far=self._passive_ticks_batch,
        )
        passive_added = [aid for aid in active if aid not in primary]
        if passive_added:
            self._passive_ticks_batch += 1
        return active

    async def _run_single_agent(self, agent_id: int, t: int) -> None:
        agent = self._resolve_agent(agent_id)
        if agent is None:
            return

        ctx = self._tick_context
        if ctx:
            agent._batch_turn_context = ctx  # noqa: SLF001
            llm = ctx.get("llm_params") or {}
            if llm:
                agent._batch_temperature = llm.get("temperature")  # noqa: SLF001
                agent._batch_max_tokens = llm.get("max_tokens")  # noqa: SLF001

        try:
            decision = await self._decide(agent, agent_id, t)
        finally:
            if ctx:
                agent._batch_turn_context = None  # noqa: SLF001
                agent._batch_temperature = None  # noqa: SLF001
                agent._batch_max_tokens = None  # noqa: SLF001

        try:
            if hasattr(agent, "last_message_seen_at"):
                agent.last_message_seen_at = int(t)
        except Exception:  # noqa: BLE001
            pass

        if decision is None or isinstance(decision, Exception):
            if isinstance(decision, Exception):
                log.warning("agent %s decide failed: %s", agent_id, decision)
            return

        for atype, akwargs in _extract_actions(decision):
            try:
                await self.dispatcher.dispatch(
                    agent_id, atype, t, **(akwargs or {})
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "dispatch(agent=%s, action=%s) failed: %s",
                    agent_id,
                    atype,
                    exc,
                )

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
