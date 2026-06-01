"""给 world-delta 里的 actor 台词批量打情绪标签——经 f05 情绪判断 agent（LLM）。

后端整合层：delta 装配好台词后，在这里统一过一遍情绪 agent，把判定结果写进每条消息的 emotion，
前端立绘据此切表情。按 (sender_id, content) 缓存：同一句话只判一次，避免每次轮询重复调 LLM。
玩家(0)/系统(-1) 的消息不判，直接 neutral。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from agent_world.drama_demo.shared.emotion import DEFAULT_EMOTION

log = logging.getLogger("agent_world.drama_demo.f12.emotion_tag")

# (sender_id, content) → emotion；轻量上限，长跑不膨胀。
_cache: Dict[Tuple[int, str], str] = {}


def tag_message_emotions(messages: List[Dict[str, Any]]) -> None:
    """就地给每条消息补 emotion 字段。只判 NPC actor 台词（sender_id>0），其余 neutral。

    已判过的(按 sender+content)复用缓存；未判的一次性批量交 f05 情绪 agent。LLM 不可用时退 neutral。
    """
    pending: List[Tuple[int, Tuple[int, str]]] = []  # (msg_index, cache_key)
    for i, m in enumerate(messages):
        sid = m.get("sender_id")
        content = str(m.get("content") or "").strip()
        if sid is None or int(sid) <= 0 or not content:
            m["emotion"] = DEFAULT_EMOTION
            continue
        key = (int(sid), content)
        cached = _cache.get(key)
        if cached is not None:
            m["emotion"] = cached
        else:
            pending.append((i, key))

    if not pending:
        return

    from agent_world.drama_demo.features.f05_story_routing import judge_emotions

    items = [
        {"id": str(i), "name": messages[i].get("sender") or "", "text": str(messages[i].get("content") or "")}
        for i, _key in pending
    ]
    verdicts = judge_emotions(items)  # {str(msg_index): emotion}

    if len(_cache) > 512:
        _cache.clear()
    for i, key in pending:
        emo = verdicts.get(str(i), DEFAULT_EMOTION)
        messages[i]["emotion"] = emo
        _cache[key] = emo
