"""ActivationScheduler 不变量测试（方案 §11 C3 对策点名要守住的）。

关键不变量：
* pick_active 永远返回非 None 列表（绕开 step.py:233 的 agent_id=0 真值陷阱）；
* 玩家 id（含 0）恒在 active 列表；
* 同地点 NPC 每拍激活；异地 NPC 仅心跳拍激活（按 id 错峰）。
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
    sched = ActivationScheduler(player_id=0, heartbeat_every=10)
    for t in range(25):
        active = sched.pick_active(world, t)
        assert active is not None and isinstance(active, list)
        assert 0 in active, f"t={t} 玩家(id=0)不在 active 列表"


def test_co_located_npc_active_every_tick() -> None:
    world = _FakeWorld({0: "farm", 3: "farm", 1: "square"})
    sched = ActivationScheduler(player_id=0, heartbeat_every=10)
    for t in range(10):
        assert 3 in sched.pick_active(world, t), "同地点 NPC 应每拍激活"


def test_remote_npc_only_on_heartbeat_ticks() -> None:
    world = _FakeWorld({0: "farm", 1: "square", 2: "saloon"})
    hb = 4
    sched = ActivationScheduler(player_id=0, heartbeat_every=hb)
    for t in range(12):
        active = sched.pick_active(world, t)
        for aid in (1, 2):
            expected = (t + aid) % hb == 0
            assert (aid in active) == expected, (
                f"t={t} 异地 NPC {aid} 激活状态错误（期望 {expected}）"
            )


def test_heartbeat_staggered_by_id() -> None:
    """两个异地 NPC 不应在同一拍一起被心跳唤醒（id 错峰）。"""
    world = _FakeWorld({0: "farm", 1: "square", 2: "saloon"})
    sched = ActivationScheduler(player_id=0, heartbeat_every=4)
    both_awake = [
        t for t in range(16)
        if {1, 2} <= set(sched.pick_active(world, t))
    ]
    assert not both_awake, f"心跳未错峰：t={both_awake} 两个异地 NPC 同拍唤醒"
