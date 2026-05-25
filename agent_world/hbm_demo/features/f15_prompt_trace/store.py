"""F15 — Runner-side trace persistence helpers."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f07_agent_control.config import (
    is_prompt_trace_enabled,
    prompt_trace_max_per_session,
    prompt_trace_truncate_chars,
)
from agent_world.persistence.world_db import WorldDB

log = logging.getLogger(__name__)


def _new_trace_id() -> str:
    return f"tr_{uuid.uuid4().hex[:12]}"


def _new_link_id() -> str:
    return f"lk_{uuid.uuid4().hex[:12]}"


def _truncate(text: str) -> str:
    limit = prompt_trace_truncate_chars()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + "\n…[truncated]"


class PromptTraceStore:
    """Thin wrapper over ``WorldDB`` trace tables."""

    def __init__(self, world_db: WorldDB) -> None:
        self._db = world_db

    @property
    def enabled(self) -> bool:
        return is_prompt_trace_enabled()

    def begin_trace(
        self,
        *,
        agent_id: int,
        at_tick: int,
        phase: Optional[str],
        player_turn: Optional[int],
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[str]:
        if not self.enabled:
            return None
        if self._db.count_llm_traces() >= prompt_trace_max_per_session():
            log.warning("F15 trace cap reached; skipping new trace")
            return None

        trace_id = _new_trace_id()
        created_at = datetime.now(timezone.utc).isoformat()
        self._db.insert_llm_trace_draft(
            trace_id=trace_id,
            agent_id=int(agent_id),
            at_tick=int(at_tick),
            phase=phase,
            player_turn=player_turn,
            model=str(model),
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=_truncate(system_prompt),
            user_prompt=_truncate(user_prompt),
            created_at=created_at,
        )
        return trace_id

    def finish_trace(
        self,
        trace_id: Optional[str],
        *,
        tool_calls: List[Dict[str, Any]],
        assistant_content: Optional[str],
    ) -> None:
        if not trace_id or not self.enabled:
            return
        self._db.update_llm_trace_result(
            trace_id,
            tool_calls_json=json.dumps(tool_calls, ensure_ascii=False),
            assistant_content=(assistant_content or None),
        )

    def link_outcome(
        self,
        *,
        trace_id: str,
        agent_id: int,
        at_tick: int,
        link_kind: str,
        ref_key: str,
    ) -> None:
        if not self.enabled:
            return
        self._db.insert_action_trace_link(
            link_id=_new_link_id(),
            trace_id=str(trace_id),
            agent_id=int(agent_id),
            at_tick=int(at_tick),
            link_kind=str(link_kind),
            ref_key=str(ref_key),
        )


__all__ = ["PromptTraceStore"]
