"""F04 stat deltas and initial values（数据驱动：维度来自活跃 Story Pack 的 meta.stats）。"""

from __future__ import annotations

from typing import Dict

from agent_world.drama_demo.features.f01_session.models import DramaSession


def initial_stats() -> Dict[str, int]:
    """各维度初始值（来自活跃 Story Pack 的 meta.stats；无则空 dict）。"""
    from agent_world.drama_demo.shared import story_config

    return story_config.initial_stats()


def apply_stat_deltas(session: DramaSession, deltas: Dict[str, int]) -> None:
    """把 {维度key: 增量} 叠加到 session.stats（泛化、无写死维度；夹取 0–100）。"""
    for key, delta in (deltas or {}).items():
        try:
            cur = int(session.stats.get(str(key), 0))
            session.stats[str(key)] = max(0, min(100, cur + int(delta)))
        except (TypeError, ValueError):
            continue
