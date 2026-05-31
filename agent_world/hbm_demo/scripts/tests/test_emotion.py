#!/usr/bin/env python3
"""情绪离散分类器单测（需求一地基，shared/emotion.py）。纯函数，离线。"""

from __future__ import annotations

import sys

from agent_world.hbm_demo.shared.emotion import (
    DEFAULT_EMOTION,
    EMOTIONS,
    classify_emotion,
    normalize_emotion,
)


def test_each_emotion_detected() -> None:
    cases = {
        "我被这帮人气炸了，简直愤怒到拍桌子": "angry",
        "心里很不安，紧张得手心冒汗，担心谈崩": "anxious",
        "听到这个消息我很难过，满是失望和无奈": "sad",
        "太好了！我非常高兴，满意得想笑": "happy",
        "我胸有成竹，稳操胜券，气定神闲地坐着": "confident",
        "他平静地记录着会议要点": "neutral",
    }
    for text, expected in cases.items():
        got = classify_emotion(text)
        assert got == expected, f"{text!r} → {got}，应为 {expected}"


def test_empty_and_unknown_default_neutral() -> None:
    assert classify_emotion("") == DEFAULT_EMOTION
    assert classify_emotion(None) == DEFAULT_EMOTION
    assert classify_emotion("今天天气不错，路上人很多") == "neutral"


def test_priority_negative_over_positive() -> None:
    # 平局时强/负面优先：1 个 angry 词(愤怒) + 1 个 happy 词(高兴) → angry 胜
    assert classify_emotion("他听完既愤怒又有点高兴") == "angry"
    # 多命中按分数取胜：愤怒+拍桌(angry=2) 压过 好笑(happy=1)
    assert classify_emotion("我愤怒得想拍桌，但又觉得有点好笑") == "angry"


def test_normalize_emotion() -> None:
    assert normalize_emotion("ANGRY") == "angry"
    assert normalize_emotion("happy") == "happy"
    assert normalize_emotion("狂喜") == DEFAULT_EMOTION  # 非受控枚举 → neutral
    assert normalize_emotion(None) == DEFAULT_EMOTION
    for e in EMOTIONS:
        assert normalize_emotion(e) == e


def test_format_state_changes_attaches_emotion() -> None:
    """f12 format_state_changes 给每条 state change 附上离散情绪标签（随 world-delta 下发前端）。"""
    from agent_world.hbm_demo.features.f12_world_sync.formatter import format_state_changes

    rows = [
        {"agent_id": 2, "content": "我被气炸了，简直愤怒", "at_tick": 5},
        {"agent_id": 3, "content": "平静地推演着技术细节", "at_tick": 6},
        {"agent_id": 4, "content": "随便写的", "at_tick": 7, "emotion": "happy"},  # 引擎透传优先
    ]
    out = format_state_changes(rows)
    assert out[0]["emotion"] == "angry", out[0]
    assert out[1]["emotion"] == "neutral", out[1]
    assert out[2]["emotion"] == "happy", out[2]  # 用透传值而非分类
    # 原字段保留
    assert out[0]["agent_id"] == 2 and out[0]["at_tick"] == 5 and out[0]["content"]


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
    print(f"\n情绪分类器：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
