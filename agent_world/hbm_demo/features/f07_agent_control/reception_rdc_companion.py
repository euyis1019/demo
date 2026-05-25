"""Ensure Phase-1 reception reports breakthroughs to Jensen via RDC, not F2F-only."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from agent_world.hbm_demo.features.f07_agent_control.batch_guard import BatchGuardState
from agent_world.hbm_demo.features.f07_agent_control.config import (
    is_reception_rdc_companion_enabled,
)

JENSEN_AGENT_ID = 2
RECEPTION_AGENT_ID = 1

_TECH_HINTS = (
    "kv",
    "显存",
    "kernel",
    "稀疏",
    "hbm",
    "repro",
    "注意力",
    "80%",
    "80％",
)


def player_text_has_tech_breakthrough(player_text: str) -> bool:
    text = str(player_text or "").lower()
    if not text.strip():
        return False
    if re.search(r"\d+\s*%", text):
        return True
    return any(hint in text for hint in _TECH_HINTS)


def build_reception_rdc_summary(*, player_text: str, f2f_content: str) -> str:
    player_text = str(player_text or "").strip()
    f2f = str(f2f_content or "").strip()
    if len(player_text) > 120:
        player_text = player_text[:120] + "…"
    if len(f2f) > 80:
        f2f = f2f[:80] + "…"
    return (
        f"黄总，前台访客刚说了：{player_text}。"
        f"我已当面回应：「{f2f}」。"
        "请您判断是否抽空见面，或我先请对方留资料。"
    )


async def ensure_reception_rdc_companion(
    dispatcher: Any,
    *,
    agent_id: int,
    t: int,
    turn_context: Optional[Dict[str, Any]],
    batch_guard: BatchGuardState,
    player_text: str,
    f2f_content: str,
) -> Optional[Dict[str, Any]]:
    """Send RDC 1→2 when inject has tech breakthrough but LLM only spoke F2F."""
    if not is_reception_rdc_companion_enabled():
        return None
    if int(agent_id) != RECEPTION_AGENT_ID:
        return None
    if not turn_context or str(turn_context.get("phase")) != "Phase 1":
        return None
    if batch_guard.rdc_count(RECEPTION_AGENT_ID) > 0:
        return None
    if not player_text_has_tech_breakthrough(player_text):
        return None

    content = build_reception_rdc_summary(
        player_text=player_text,
        f2f_content=f2f_content,
    )
    try:
        from agent_world.world.dispatcher import ActionType

        action_type = ActionType.SEND_MESSAGE
    except Exception:  # noqa: BLE001
        action_type = "send_message"

    result = await dispatcher.dispatch(
        RECEPTION_AGENT_ID,
        action_type,
        int(t),
        target=JENSEN_AGENT_ID,
        content=content,
    )
    if result and result.get("success"):
        batch_guard.mark_rdc(RECEPTION_AGENT_ID, JENSEN_AGENT_ID)
    return result


__all__ = [
    "build_reception_rdc_summary",
    "ensure_reception_rdc_companion",
    "player_text_has_tech_breakthrough",
]
