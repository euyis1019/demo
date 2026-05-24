"""L5 tool-call filtering for HBM agents."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from agent_world.hbm_demo.features.f07_agent_control.matrix import (
    allowed_tools_for,
    is_move_allowed,
)

log = logging.getLogger("agent_world.hbm_demo.f07")

ToolCall = Any


def _allowed_set(ctx: Dict[str, Any], agent_id: int) -> Set[str]:
    by_agent = ctx.get("allowed_tools_by_agent") or {}
    raw = by_agent.get(str(agent_id), by_agent.get(agent_id))
    if raw is not None:
        return set(raw)
    phase = str(ctx.get("phase", "Phase 1"))
    turn = int(ctx.get("player_turn", 1))
    return allowed_tools_for(agent_id, phase, turn)


def filter_tool_calls(
    tool_calls: List[ToolCall],
    *,
    agent_id: int,
    ctx: Dict[str, Any] | None,
) -> List[ToolCall]:
    """Drop or replace tool calls blocked by ABCS L5 rules."""
    if not ctx or not ctx.get("enabled", True):
        return tool_calls

    phase = str(ctx.get("phase", "Phase 1"))
    turn = int(ctx.get("player_turn", 1))
    allowed = _allowed_set(ctx, agent_id)
    out: List[ToolCall] = []

    for tc in tool_calls:
        name = getattr(tc, "tool_name", None) or getattr(tc, "name", "")
        if name == "request_move" and not is_move_allowed(agent_id, phase, turn):
            log.debug(
                "ABCS blocked request_move agent=%s phase=%s turn=%s",
                agent_id,
                phase,
                turn,
            )
            out.append(_replace(tc, "do_nothing", {}))
            continue
        if name not in allowed:
            log.debug(
                "ABCS blocked tool=%s agent=%s allowed=%s",
                name,
                agent_id,
                sorted(allowed),
            )
            out.append(_replace(tc, "do_nothing", {}))
            continue
        out.append(tc)

    return out or tool_calls


def _replace(original: ToolCall, tool_name: str, args: Dict[str, Any]) -> ToolCall:
    try:
        from agent_world.demo.demo_agent import _ToolCall

        return _ToolCall(tool_name=tool_name, args=args)
    except Exception:  # noqa: BLE001
        class _Shim:
            def __init__(self, n: str, a: Dict[str, Any]) -> None:
                self.tool_name = n
                self.args = a

        return _Shim(tool_name, args)
