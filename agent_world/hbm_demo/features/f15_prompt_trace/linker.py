"""F15 — map dispatch outcomes to trace link rows."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f15_prompt_trace.refs import (
    f2f_ref_key,
    grp_ref_key,
    noop_ref_key,
    rdc_ref_key,
    state_ref_key,
)
from agent_world.hbm_demo.features.f15_prompt_trace.store import PromptTraceStore
from agent_world.persistence.world_db import WorldDB

log = logging.getLogger(__name__)


def _action_name(action_type: Any) -> str:
    return str(
        getattr(action_type, "tool_name", None)
        or getattr(action_type, "value", None)
        or getattr(action_type, "name", None)
        or action_type
        or ""
    ).lower().replace("-", "_")


async def record_action_links(
    world_db: Optional[WorldDB],
    *,
    trace_id: Optional[str],
    agent_id: int,
    t: int,
    action_type: Any,
    action_kwargs: Dict[str, Any],
    dispatch_result: Optional[Dict[str, Any]],
    place_id: Optional[str],
) -> None:
    store = PromptTraceStore(world_db) if world_db is not None else None
    if store is None or not store.enabled:
        return
    if not trace_id:
        log.debug(
            "F15 skip link: missing trace_id agent=%s t=%s action=%s",
            agent_id,
            t,
            _action_name(action_type),
        )
        return

    name = _action_name(action_type)
    result = dispatch_result or {}
    # F2F/RDC/GRP: link the LLM decision even when bus delivery fails (φ reject).
    # Prompt Inspector shows what the agent chose to send, not deliverability.
    comm_actions = frozenset({"speak_to_local", "send_message", "send_to_group"})
    if name not in comm_actions:
        if not result.get("success") and not result.get("noop"):
            return

    try:
        if name == "speak_to_local":
            if not place_id:
                return
            store.link_outcome(
                trace_id=trace_id,
                agent_id=int(agent_id),
                at_tick=int(t),
                link_kind="f2f",
                ref_key=f2f_ref_key(str(place_id), int(t), int(agent_id)),
            )
        elif name == "send_message":
            target = action_kwargs.get("target")
            if target is None:
                return
            store.link_outcome(
                trace_id=trace_id,
                agent_id=int(agent_id),
                at_tick=int(t),
                link_kind="rdc",
                ref_key=rdc_ref_key(int(t), int(agent_id), int(target)),
            )
        elif name == "send_to_group":
            group_id = action_kwargs.get("group_id")
            if group_id is None:
                return
            store.link_outcome(
                trace_id=trace_id,
                agent_id=int(agent_id),
                at_tick=int(t),
                link_kind="grp",
                ref_key=grp_ref_key(int(t), int(agent_id), int(group_id)),
            )
        elif name == "update_state":
            content = str(action_kwargs.get("new_state") or "")
            store.link_outcome(
                trace_id=trace_id,
                agent_id=int(agent_id),
                at_tick=int(t),
                link_kind="state",
                ref_key=state_ref_key(int(t), int(agent_id), content),
            )
        elif name == "do_nothing" or result.get("noop"):
            store.link_outcome(
                trace_id=trace_id,
                agent_id=int(agent_id),
                at_tick=int(t),
                link_kind="do_nothing",
                ref_key=noop_ref_key(int(t), int(agent_id)),
            )
        elif name == "relation_change":
            store.link_outcome(
                trace_id=trace_id,
                agent_id=int(agent_id),
                at_tick=int(t),
                link_kind="relation",
                ref_key=f"rel:{t}:{agent_id}",
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("F15 link_outcome failed agent=%s: %s", agent_id, exc)


__all__ = ["record_action_links"]
