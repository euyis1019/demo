"""F07-E1 — scripted player-facing F2F fallback when LLM skips speak_to_local."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f07_agent_control.batch_guard import BatchGuardState
from agent_world.hbm_demo.features.f07_agent_control.config import (
    first_f2f_required_agents,
    is_f07_enabled,
    is_reception_f2f_fallback_enabled,
    scripted_f2f_fallback_enabled,
)
from agent_world.hbm_demo.features.f07_agent_control.player_facing_f2f import (
    emit_player_facing_f2f,
)

_FALLBACK_TEMPLATES: Dict[str, str] = {
    "Phase 1": "您提到的{kw}，我需要跟黄总确认，请稍等。",
    "Phase 2": "{kw}——外面的人在等，你继续。",
    "Phase 4": "{kw}，我们可以再谈条件。",
}

_DEFAULT_PLACE_BY_PHASE: Dict[str, str] = {
    "Phase 1": "nvidia_reception",
    "Phase 2": "jensen_private_room",
    "Phase 4": "negotiation_room",
}

_FALLBACK_AGENT_BY_PHASE: Dict[str, int] = {
    "Phase 1": 1,
    "Phase 2": 2,
    "Phase 4": 2,
}

RECEPTION_AGENT_ID = 1

_KEYWORD_HINTS = (
    "显存",
    "KV",
    "算法",
    "kernel",
    "稀疏",
    "HBM",
    "注意力",
    "seed",
    "equity",
    "估值",
)


def extract_player_keyword(player_text: str) -> str:
    text = str(player_text or "").strip()
    text = re.sub(r"^玩家说[：:]\s*", "", text)
    text = re.sub(r"^玩家\s*", "", text).strip()
    match = re.search(r"\d+%", text)
    if match:
        return match.group(0)
    for hint in _KEYWORD_HINTS:
        if hint in text:
            return hint
    if len(text) > 20:
        return text[:20] + "…"
    return text or "您的诉求"


def build_fallback_content(phase: str, player_text: str) -> str:
    template = _FALLBACK_TEMPLATES.get(
        str(phase), "您提到的{kw}，请稍等。"
    )
    return template.format(kw=extract_player_keyword(player_text))


def _fallback_agent_for_phase(phase: str) -> Optional[int]:
    required = first_f2f_required_agents(phase)
    if required:
        return int(required[0])
    return _FALLBACK_AGENT_BY_PHASE.get(str(phase))


def _inject_expects_reception_f2f(turn_context: Dict[str, Any]) -> bool:
    if not str(turn_context.get("player_text") or "").strip():
        return False
    inject_ids = {int(x) for x in (turn_context.get("inject_agent_ids") or [])}
    return RECEPTION_AGENT_ID in inject_ids


async def apply_batch_f2f_fallback(
    world_db: Any,
    *,
    turn_context: Optional[Dict[str, Any]],
    batch_guard: BatchGuardState,
    t: int,
) -> int:
    """Emit one scripted F2F for the phase inject target if still missing."""
    if not is_f07_enabled() or not turn_context:
        return 0
    if not is_reception_f2f_fallback_enabled() and not scripted_f2f_fallback_enabled():
        return 0
    if not _inject_expects_reception_f2f(turn_context):
        return 0

    phase = str(turn_context.get("phase", "Phase 1"))
    agent_id = _fallback_agent_for_phase(phase)
    if agent_id is None:
        return 0
    if batch_guard.has_f2f(agent_id):
        return 0

    place_id = str(
        turn_context.get("place_id") or _DEFAULT_PLACE_BY_PHASE.get(phase, "")
    )
    if not place_id or world_db is None:
        return 0

    content = build_fallback_content(
        phase, str(turn_context.get("player_text") or "")
    )
    await emit_player_facing_f2f(
        world_db,
        sender_id=agent_id,
        place_id=place_id,
        content=content,
        t=int(t),
    )
    batch_guard.mark_f2f(agent_id)
    return 1


__all__ = [
    "apply_batch_f2f_fallback",
    "build_fallback_content",
    "extract_player_keyword",
]
