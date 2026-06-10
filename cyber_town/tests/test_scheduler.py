"""ActivationScheduler 不变量测试（W3 全员每拍激活版）。

关键不变量：
* pick_active 永远返回非 None 列表（绕开 step.py:233 的 agent_id=0 真值陷阱）；
* 玩家 id（含 0）恒在 active 列表；
* 全员每拍激活：所有 NPC 每拍都在列表（行动时机不被调度器代理）。
"""

from __future__ import annotations

from typing import Dict

from cyber_town.backend.scheduler import ActivationScheduler


class _FakeWorld:
    """最小 world 替身：agents 映射 + location_of。"""

    def __init__(self, locations: Dict[int, str]) -> None:
        self.agents = {aid: object() for aid in locations}
        self._loc = locations

    def location_of(self, aid: int) -> str:
        return self._loc[int(aid)]


def test_player_zero_always_active_and_non_none() -> None:
    world = _FakeWorld({0: "farm", 1: "square", 2: "saloon", 3: "farm"})
    sched = ActivationScheduler(player_id=0)
    for t in range(25):
        active = sched.pick_active(world, t)
        assert active is not None and isinstance(active, list)
        assert 0 in active, f"t={t} 玩家(id=0)不在 active 列表"


def test_all_npcs_active_every_tick() -> None:
    """W3：全员每拍激活——任何 NPC 任何拍都不被代理「何时能思考」。"""
    world = _FakeWorld({0: "farm", 1: "square", 2: "saloon", 3: "farm"})
    sched = ActivationScheduler(player_id=0)
    for t in range(12):
        active = set(sched.pick_active(world, t))
        assert active == {0, 1, 2, 3}, f"t={t} 应全员激活：{active}"
