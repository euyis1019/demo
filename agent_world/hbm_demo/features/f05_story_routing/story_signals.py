"""Structured story_advance signals — read world.db (dev_logs/30 §4.4.5 · dev_logs/31 Phase 5)."""

from __future__ import annotations

from typing import Any, FrozenSet, Optional, Tuple

VALID_STORY_SIGNALS: Tuple[str, ...] = (
    "approve_visitor",
    "reject_visitor",
    "return_to_negotiation",
    "expel_ceos",
    "offer_join",
    "offer_seed",
)

_SIGNAL_SET: FrozenSet[str] = frozenset(VALID_STORY_SIGNALS)


def normalize_story_signal(raw: Any) -> Optional[str]:
    text = str(raw or "").strip().lower()
    if text in _SIGNAL_SET:
        return text
    return None


def has_story_signal(
    db: Any,
    signal: str,
    *,
    since_t: int,
    t_now: int,
    agent_id: Optional[int] = None,
) -> bool:
    """Return True if ``signal`` was logged in (since_t, t_now]."""
    if db is None or not hasattr(db, "fetch_story_advance_since"):
        return False
    norm = normalize_story_signal(signal)
    if not norm:
        return False
    rows = db.fetch_story_advance_since(
        int(since_t),
        int(t_now),
        signal=norm,
        agent_id=agent_id,
    )
    return len(rows) > 0


__all__ = [
    "VALID_STORY_SIGNALS",
    "has_story_signal",
    "normalize_story_signal",
]
