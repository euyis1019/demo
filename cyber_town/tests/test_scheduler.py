"""ActivationScheduler 不变量测试（W3 全员每拍激活版）。

关键不变量：
* pick_active 永远返回非 None 列表（绕开 step.py:233 的 agent_id=0 真值陷阱）；
* 玩家 id（含 0）恒在 active 列表；
* 全员每拍激活：所有 NPC 每拍都在列表（行动时机不被调度器代理）。
"""

from __future__ import annotations

from typing import Dict

from cyber_town.backend.runtime.scheduler import ActivationScheduler


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


class _FakeDM:
    def __init__(self, channel_type: str = "RDC") -> None:
        self.channel_type = channel_type


class _FakeDB:
    """world_db 替身：可配置某 agent 的未读私信。"""

    def __init__(self, unread: Dict[int, list]) -> None:
        self._unread = unread

    def fetch_arrived_for(self, aid: int, t: int, last_seen: int = -1) -> list:
        return self._unread.get(int(aid), [])


class _FakeAgent:
    last_message_seen_at = -1


class _FakeWorldDB(_FakeWorld):
    """带 world_db 与 agent 对象的替身（W7 紧急唤醒用）。"""

    def __init__(self, locations: Dict[int, str], unread: Dict[int, list]) -> None:
        super().__init__(locations)
        self.agents = {aid: _FakeAgent() for aid in locations}
        self.world_db = _FakeDB(unread)


def test_unread_dm_urgent_wakeup_bypasses_tier() -> None:
    """W7：sleep 档 NPC 有未读私信 → 本拍紧急唤醒，不等档位。"""
    world = _FakeWorldDB({0: "farm", 1: "square"}, unread={1: [_FakeDM("RDC")]})
    sched = ActivationScheduler(player_id=0, interval_provider=lambda _n: 12)
    # 选一个按档位不会激活的拍：(t + 1) % 12 != 0
    t = 5
    assert (t + 1) % 12 != 0
    assert 1 in sched.pick_active(world, t)


def test_no_unread_dm_keeps_tier_schedule() -> None:
    """无未读私信时，sleep 档 NPC 仍按档位错峰（不被误唤醒）。"""
    world = _FakeWorldDB({0: "farm", 1: "square"}, unread={})
    sched = ActivationScheduler(player_id=0, interval_provider=lambda _n: 12)
    t = 5
    assert 1 not in sched.pick_active(world, t)


def test_non_rdc_messages_do_not_trigger_wakeup() -> None:
    """群聊消息不触发紧急唤醒（只有私信算「手机响了」）。"""
    world = _FakeWorldDB({0: "farm", 1: "square"}, unread={1: [_FakeDM("GRP")]})
    sched = ActivationScheduler(player_id=0, interval_provider=lambda _n: 12)
    assert 1 not in sched.pick_active(world, 5)
