"""HBM demo WorldStep — parallel LLM decisions within each place + ABCS L3."""

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

    def set_tick_context(self, ctx: Optional[Dict[str, Any]]) -> None:
        """Set ABCS TurnContext for the next inject tick loop (L3/L5)."""
        self._tick_context = dict(ctx) if ctx else None
        if ctx and ctx.get("enabled", True):
            setattr(self.world, "_hbm_tick_context", ctx)
        elif hasattr(self.world, "_hbm_tick_context"):
            delattr(self.world, "_hbm_tick_context")

    def clear_tick_context(self) -> None:
        self.set_tick_context(None)

    def _pick_active(self, t: int) -> List[int]:
        ctx = self._tick_context
        if ctx and ctx.get("enabled", True):
            active = [int(a) for a in (ctx.get("active_agent_ids") or [])]
            passive = [int(a) for a in (ctx.get("passive_agent_ids") or [])]
            for aid in passive:
                if aid not in active and self._agent_has_pending_work(aid, t):
                    active.append(aid)
            if active:
                return active
        return super()._pick_active(t)

    def _agent_has_pending_work(self, agent_id: int, t: int) -> bool:
        agent = self._resolve_agent(agent_id)
        if agent is None:
            return False
        memory = getattr(agent, "player_memory", None)
        if memory:
            return True
        if self.world_db is None:
            return False
        last_seen = int(getattr(agent, "last_message_seen_at", -1))
        try:
            incoming = self.world_db.fetch_arrived_for(agent_id, t, last_seen)
            return bool(incoming)
        except Exception:  # noqa: BLE001
            return False

    async def _run_single_agent(self, agent_id: int, t: int) -> None:
        agent = self._resolve_agent(agent_id)
        if agent is None:
            return

        decision = await self._decide(agent, agent_id, t)

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
