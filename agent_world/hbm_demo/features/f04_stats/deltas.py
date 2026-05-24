"""F04 stat deltas and initial values."""

from __future__ import annotations

from typing import Dict

from agent_world.hbm_demo.features.f01_session.constants import INITIAL_STATS
from agent_world.hbm_demo.features.f01_session.models import HbmSession


def initial_stats() -> Dict[str, int]:
    return dict(INITIAL_STATS)


def apply_stat_deltas(session: HbmSession, deltas: Dict[str, int]) -> None:
    session.stats["vision"] = max(
        0, min(999, session.stats["vision"] + int(deltas.get("vision_delta", 0)))
    )
    session.stats["execution"] = max(
        0, min(999, session.stats["execution"] + int(deltas.get("execution_delta", 0)))
    )
    session.stats["trust"] = max(
        0, min(999, session.stats["trust"] + int(deltas.get("trust_delta", 0)))
    )
    session.stats["burnout"] = max(
        0, min(100, session.stats["burnout"] + int(deltas.get("burnout_delta", 0)))
    )
