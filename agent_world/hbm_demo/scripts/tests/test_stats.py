#!/usr/bin/env python3
"""数值系统回归钉死（需求四 / dev_logs：原先无打分回归测试）。

LLM 打分值本身不可断言（依赖模型），但**启发式回退**与 **clamp** 是确定性的，钉死它们，
后续加强（burnout 消费等）不致破坏现有行为。离线，不连 LLM。
"""

from __future__ import annotations

import sys

import agent_world.hbm_demo.game_service  # noqa: F401  建立正确加载顺序，避开 f04↔f01 循环导入
from agent_world.hbm_demo.features.f04_stats.deltas import apply_stat_deltas
from agent_world.hbm_demo.features.f04_stats.scoring import _heuristic_stats


class _FakeSession:
    def __init__(self, **stats: int) -> None:
        self.stats = {"vision": 0, "execution": 0, "trust": 10, "burnout": 0, **stats}


def test_heuristic_tech_keyword() -> None:
    d = _heuristic_stats(_FakeSession(), "我们的算法能把显存占用降低 80%")
    assert d == {"vision_delta": 5, "execution_delta": 4, "trust_delta": 1, "burnout_delta": 0}, d


def test_heuristic_short_text_burnout() -> None:
    d = _heuristic_stats(_FakeSession(), "嗯")  # <8 字符
    assert d == {"vision_delta": 0, "execution_delta": 0, "trust_delta": 0, "burnout_delta": 1}, d


def test_heuristic_default_small_gain() -> None:
    d = _heuristic_stats(_FakeSession(), "我想和你好好聊聊合作的事情吧")  # 无技术词、>=8 字
    assert d == {"vision_delta": 1, "execution_delta": 1, "trust_delta": 0, "burnout_delta": 0}, d


def test_apply_clamps_upper_bounds() -> None:
    s = _FakeSession(vision=998, execution=998, trust=998, burnout=99)
    apply_stat_deltas(s, {"vision_delta": 10, "execution_delta": 10, "trust_delta": 10, "burnout_delta": 10})
    assert s.stats["vision"] == 999 and s.stats["execution"] == 999  # [0,999]
    assert s.stats["trust"] == 999
    assert s.stats["burnout"] == 100  # burnout 上限 100


def test_apply_clamps_lower_bound_zero() -> None:
    s = _FakeSession(vision=2, execution=0, trust=1, burnout=3)
    apply_stat_deltas(s, {"vision_delta": -10, "execution_delta": -5, "trust_delta": -10, "burnout_delta": -10})
    assert s.stats["vision"] == 0 and s.stats["execution"] == 0
    assert s.stats["trust"] == 0 and s.stats["burnout"] == 0  # 不为负


def test_apply_normal_accumulation() -> None:
    s = _FakeSession()
    apply_stat_deltas(s, {"vision_delta": 5, "execution_delta": 4, "trust_delta": 1, "burnout_delta": 0})
    assert s.stats == {"vision": 5, "execution": 4, "trust": 11, "burnout": 0}


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
    print(f"\n数值系统：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
