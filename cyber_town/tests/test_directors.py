"""管理类 agent（W5 导演）测试：不调真 LLM，用 mock 客户端。

关键不变量：
* 激活导演：首份策略全 high；非法输出沿用旧策略；漏写 NPC 安全侧补 high；
  scheduler 接 interval_provider 后玩家恒在、high 每拍在、low/sleep 按 id 错峰、
  provider 抛异常回落每拍。
* 世界事件导演：事件有时限到期消散；event=null 表示平常无事；
  render_for_npc 只在有事件时产出附加段。
* base.call_llm_json：LLM 抛异常 / 非 JSON 输出 → 返回 None（fail-soft）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import pytest

from cyber_town.backend.directors import ActivationDirector, WorldDirector
from cyber_town.backend.llm.json_call import call_llm_json
from cyber_town.backend.runtime.scheduler import ActivationScheduler


# ---------------------------------------------------------------- mock LLM

class _FakeLLM:
    """openai AsyncClient 替身：按预置文本依次应答，可设抛错。"""

    def __init__(self, replies: list, raise_exc: bool = False) -> None:
        self._replies = list(replies)
        self._raise = raise_exc
        self.chat = self
        self.completions = self

    async def create(self, **_kw: Any) -> Any:
        if self._raise:
            raise RuntimeError("boom")
        text = self._replies.pop(0) if self._replies else "{}"

        class _Msg:
            content = text

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _FakeWorld:
    def __init__(self, locations: Dict[int, str]) -> None:
        self.agents = {aid: object() for aid in locations}
        self._loc = locations

    def location_of(self, aid: int) -> str:
        return self._loc[int(aid)]


# ---------------------------------------------------------------- base

def test_call_llm_json_fail_soft() -> None:
    async def run() -> None:
        # LLM 抛异常 → None
        assert await call_llm_json(_FakeLLM([], raise_exc=True), "m", "s", "u") is None
        # 非 JSON 输出 → None
        assert await call_llm_json(_FakeLLM(["我拒绝输出 JSON"]), "m", "s", "u") is None
        # 正常 JSON（带废话包裹）→ 解析成功
        data = await call_llm_json(
            _FakeLLM(['好的，如下：{"a": 1} 完毕']), "m", "s", "u")
        assert data == {"a": 1}

    asyncio.run(run())


# ---------------------------------------------------------------- 激活导演

def test_activation_director_default_all_high() -> None:
    d = ActivationDirector(_FakeLLM([]), "m", [1, 2, 3])
    for nid in (1, 2, 3):
        assert d.interval_of(nid) == 1
    # 未知 id 也安全侧 high
    assert d.interval_of(99) == 1


def test_activation_director_applies_and_backfills() -> None:
    reply = json.dumps({"tiers": {"1": "low", "2": "sleep"}, "reason": "test"})
    d = ActivationDirector(_FakeLLM([reply]), "m", [1, 2, 3])

    asyncio.run(d._decide(None, 10))  # noqa: SLF001 — 直测决策体，绕过摘要

    assert d.interval_of(1) == 4      # low
    assert d.interval_of(2) == 12     # sleep
    assert d.interval_of(3) == 1      # 漏写 → 补 high


def test_activation_director_keeps_policy_on_bad_output() -> None:
    d = ActivationDirector(_FakeLLM(["不是 JSON"]), "m", [1, 2])
    d.tiers = {1: "low", 2: "high"}
    asyncio.run(d._decide(None, 10))  # noqa: SLF001
    assert d.tiers == {1: "low", 2: "high"}  # 沿用旧策略


def test_scheduler_with_interval_provider() -> None:
    world = _FakeWorld({0: "farm", 1: "square", 2: "saloon", 3: "farm"})
    intervals = {1: 1, 2: 4, 3: 12}
    sched = ActivationScheduler(player_id=0,
                                interval_provider=lambda nid: intervals[nid])
    seen: Dict[int, int] = {1: 0, 2: 0, 3: 0}
    for t in range(48):
        active = sched.pick_active(world, t)
        assert active is not None and 0 in active   # 玩家恒在 + 非 None 契约
        assert 1 in active                          # high 每拍在
        for nid in (2, 3):
            if nid in active:
                seen[nid] += 1
                assert (t + nid) % intervals[nid] == 0  # 按 id 错峰
    assert seen[2] == 48 // 4 and seen[3] == 48 // 12   # 保底唤醒，不冻结


def test_scheduler_provider_exception_falls_back_to_every_tick() -> None:
    world = _FakeWorld({0: "farm", 1: "square"})

    def bad_provider(_nid: int) -> int:
        raise RuntimeError("director down")

    sched = ActivationScheduler(player_id=0, interval_provider=bad_provider)
    for t in range(5):
        assert 1 in sched.pick_active(world, t)     # 安全侧回落每拍


# ---------------------------------------------------------------- 世界事件导演

def test_world_director_event_lifecycle() -> None:
    reply = json.dumps({"event": "飘起细雨，泥路有些滑",
                        "duration_ticks": 10, "reason": "test"})
    d = WorldDirector(_FakeLLM([reply]), "m")

    class _Asm:
        scenario = {"clock": {"start_time": "08:00", "minutes_per_tick": 5}}

    asyncio.run(d._decide(_Asm(), 24))  # noqa: SLF001

    assert d.current_event(25) == "飘起细雨，泥路有些滑"
    assert "# 此刻的天时人事" in d.render_for_npc(25)
    # 到期自动消散
    assert d.current_event(24 + 10) is None
    assert d.render_for_npc(24 + 10) == ""


def test_world_director_null_event_means_ordinary() -> None:
    reply = json.dumps({"event": None, "reason": "世界平平常常"})
    d = WorldDirector(_FakeLLM([reply]), "m")

    class _Asm:
        scenario = {"clock": {}}

    asyncio.run(d._decide(_Asm(), 24))  # noqa: SLF001
    assert d.current_event(25) is None
    assert d.render_for_npc(25) == ""
