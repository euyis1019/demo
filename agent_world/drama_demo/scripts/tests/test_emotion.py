#!/usr/bin/env python3
"""情绪枚举/归一 + 新情绪链路单测（shared/emotion.py + f12 emotion_tag）。纯离线。

情绪标签现由 f05 情绪判断 agent(LLM) 在台词上打标（emotion_tag）；旧关键词分类(classify_emotion)已删。
本单测只覆盖**离线**部分：枚举归一、state change 不再分类(neutral)、tagger 对玩家/系统/空内容的兜底。
真正的 LLM 判定由运行期探针验证。
"""

from __future__ import annotations

import sys

from agent_world.drama_demo.shared.emotion import DEFAULT_EMOTION, EMOTIONS, normalize_emotion


def test_emotions_enum() -> None:
    assert DEFAULT_EMOTION == "neutral"
    for e in ("neutral", "happy", "angry", "sad", "anxious", "confident"):
        assert e in EMOTIONS, e
    assert len(EMOTIONS) == 6


def test_normalize_emotion() -> None:
    assert normalize_emotion("ANGRY") == "angry"
    assert normalize_emotion("happy") == "happy"
    assert normalize_emotion("狂喜") == DEFAULT_EMOTION  # 非受控枚举 → neutral
    assert normalize_emotion(None) == DEFAULT_EMOTION
    for e in EMOTIONS:
        assert normalize_emotion(e) == e


def test_state_changes_no_keyword_classify() -> None:
    """情绪不再在 OS 状态变更上按关键词分类——一律 neutral，原字段保留。"""
    from agent_world.drama_demo.features.f12_world_sync.formatter import format_state_changes

    out = format_state_changes([{"agent_id": 2, "content": "我被气炸了，简直愤怒", "at_tick": 5}])
    assert out[0]["emotion"] == DEFAULT_EMOTION, out[0]
    assert out[0]["agent_id"] == 2 and out[0]["at_tick"] == 5 and out[0]["content"]


def test_tag_message_emotions_non_actor_neutral() -> None:
    """玩家(0)/系统(-1)/空内容的消息不送情绪 agent，直接 neutral；就地补 emotion 字段。"""
    from agent_world.drama_demo.features.f12_world_sync.emotion_tag import tag_message_emotions

    msgs = [
        {"sender_id": 0, "sender": "我", "content": "你好"},
        {"sender_id": -1, "sender": "系统", "content": "系统提示"},
        {"sender_id": 3, "sender": "甲", "content": "   "},  # 空内容
    ]
    tag_message_emotions(msgs)
    for m in msgs:
        assert m["emotion"] == DEFAULT_EMOTION, m


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
    print(f"\n情绪链路：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
