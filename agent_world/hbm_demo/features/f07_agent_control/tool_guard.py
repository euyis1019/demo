"""F07 L5 — tool whitelist / MOVE interception."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from agent_world.hbm_demo.features.f07_agent_control.config import (
    first_f2f_required_agents,
    is_experience_hardening,
    is_f07_enabled,
    load_turn_control,
    rdc_quota_for,
)

log = logging.getLogger("agent_world.hbm_demo.f07.tool_guard")

_MATRIX_PATH = Path(__file__).resolve().parent / "tool_matrix.yaml"

_PASSIVE_PROB = {"low": 0.25, "medium": 0.50, "high": 0.75}


@lru_cache(maxsize=1)
def _load_tool_matrix() -> Dict[str, Any]:
    if not _MATRIX_PATH.is_file():
        return {}
    with _MATRIX_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _phase_block(phase: str) -> Dict[str, Any]:
    phases = (_load_tool_matrix().get("phases") or {})
    return dict(phases.get(phase) or phases.get("Phase 1") or {})


def allowed_tools_for(agent_id: int, turn_context: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Return allowed tool names, or None if F07 disabled / no context."""
    if not is_f07_enabled() or not turn_context:
        return None
    phase = str(turn_context.get("phase", "Phase 1"))
    block = _phase_block(phase)
    agents = block.get("agents") or {}
    allowed = agents.get(int(agent_id)) or agents.get(str(agent_id))
    if allowed is None:
        return []
    return list(allowed)


def is_tool_allowed(
    agent_id: int,
    tool_name: str,
    turn_context: Optional[Dict[str, Any]],
) -> bool:
    if not is_f07_enabled() or not turn_context:
        return True
    name = str(tool_name or "").strip()
    if not name:
        return False

    phase = str(turn_context.get("phase", "Phase 1"))
    player_turn = int(turn_context.get("player_turn", 1))
    block = _phase_block(phase)

    if name == "request_move":
        if int(agent_id) == 1:
            return False
        if int(agent_id) == 7 and player_turn < 16:
            return False
        if phase in ("Phase 1", "Phase 2", "Phase 4"):
            return False
        if not block.get("move_allowed", False):
            return False

    allowed = allowed_tools_for(agent_id, turn_context) or []
    return name in allowed


def filter_tool_calls(
    agent_id: int,
    turn_context: Optional[Dict[str, Any]],
    tool_calls: Sequence[Any],
    *,
    batch_guard: Optional[Any] = None,
) -> List[Any]:
    """Replace disallowed tool calls with ``do_nothing``."""
    if not is_f07_enabled() or not turn_context or not tool_calls:
        return list(tool_calls)

    # E1 — before matrix guard: required agents must F2F before other tools.
    if is_experience_hardening() and batch_guard is not None:
        phase = str(turn_context.get("phase", "Phase 1"))
        required = first_f2f_required_agents(phase)
        if int(agent_id) in required and not batch_guard.has_f2f(int(agent_id)):
            first_allowed = frozenset({"speak_to_local", "do_nothing"})
            for tc in tool_calls:
                name = str(
                    getattr(tc, "tool_name", None) or getattr(tc, "name", "")
                )
                if name not in first_allowed:
                    log.info(
                        "F07-E1 first_action_guard: agent %s blocked %s "
                        "before F2F (phase=%s)",
                        agent_id,
                        name,
                        phase,
                    )
                    from agent_world.demo.demo_agent import _ToolCall

                    return [_ToolCall(tool_name="do_nothing", args={})]

    out: List[Any] = []
    for tc in tool_calls:
        name = str(
            getattr(tc, "tool_name", None) or getattr(tc, "name", "")
        )
        # E2 — after first-action guard, before matrix guard.
        if (
            is_experience_hardening()
            and batch_guard is not None
            and name == "send_message"
        ):
            phase = str(turn_context.get("phase", "Phase 1"))
            quota = rdc_quota_for(int(agent_id), phase)
            if quota is not None and batch_guard.rdc_count(int(agent_id)) >= quota:
                log.info(
                    "F07-E2 rdc_quota: agent %s blocked send_message "
                    "(count=%s quota=%s phase=%s)",
                    agent_id,
                    batch_guard.rdc_count(int(agent_id)),
                    quota,
                    phase,
                )
                from agent_world.demo.demo_agent import _ToolCall

                return [_ToolCall(tool_name="do_nothing", args={})]

        if is_tool_allowed(agent_id, name, turn_context):
            out.append(tc)
        else:
            log.info(
                "F07 tool_guard: agent %s blocked %s (phase=%s)",
                agent_id,
                name,
                turn_context.get("phase"),
            )
            from agent_world.demo.demo_agent import _ToolCall

            return [_ToolCall(tool_name="do_nothing", args={})]
    return out or list(tool_calls)


def passive_tick_probability(phase: str) -> float:
    cfg = load_turn_control()
    phases = cfg.get("phases") or {}
    block = phases.get(phase) or {}
    key = str(block.get("passive_tick_probability", "medium"))
    return _PASSIVE_PROB.get(key, 0.5)
