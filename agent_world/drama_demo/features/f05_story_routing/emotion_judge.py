"""情绪判断 agent（运行期管理层）：读 actor 这句台词，判一个受控情绪标签。

替代旧的关键词兜底分类（shared/emotion.classify_emotion 已删）——交给 LLM 读懂整句的真实情绪
与潜台词（嘴上客气心里恼火→angry；强作镇定其实慌→anxious），而不是数关键词。和 f05 导演同层
（运行期 LLM 判断，无硬规则），复用同一套 client 配置。

批量：一次判一批台词（每条一个标签），返回 {item_id: emotion}。出错/空 → {}（调用方按 neutral 兜底）。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from agent_world.drama_demo.shared.emotion import DEFAULT_EMOTION, EMOTIONS, normalize_emotion

log = logging.getLogger("agent_world.drama_demo.f05.emotion_judge")

_SYSTEM = (
    "你是一部互动剧的「情绪判读 / emotion manager」。逐条读每个角色这句台词（结合用词、语气、潜台词），"
    "判断他说这句时此刻流露的情绪，从这六个里**选一个**：\n"
    "neutral(平静无明显情绪) / happy(喜悦) / angry(愤怒) / sad(悲伤) / anxious(焦虑不安) / confident(自信笃定)。\n"
    "要读懂整句的真实情绪与潜台词：嘴上客气心里恼火→angry；强作镇定其实发慌→anxious；皮笑肉不笑别误判 happy。"
    "确实平淡、就事论事、无明显情绪波动才给 neutral。\n"
    '严格只输出一行 JSON：{"emotions":[{"id":"条目id原样","emotion":"上面六选一"}, ...]}，每个条目都要给。'
)


def _client_and_cfg():
    from openai import OpenAI

    from agent_world.drama_demo.core.runner.kernel import resolve_api_key
    from agent_world.drama_demo.shared import story_config

    llm_cfg = dict(story_config.active_pack().meta.get("llm") or {})
    client = OpenAI(
        api_key=resolve_api_key(llm_cfg),
        base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
    )
    return client, llm_cfg


def _parse_json(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        s = m.group(0)
    try:
        data = json.loads(s)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def judge_emotions(items: List[Dict[str, Any]]) -> Dict[str, str]:
    """给一批台词判情绪。items: [{"id": str, "name": str, "text": str}]。
    返回 {id: emotion}（已归一到 EMOTIONS）。空/出错 → {}。"""
    rows = [x for x in (items or []) if str(x.get("text") or "").strip()]
    if not rows:
        return {}
    user = (
        "判断下面每条台词此刻流露的情绪（六选一）：\n"
        + "\n".join(f'- id={x["id"]}｜{x.get("name") or x["id"]}：{str(x["text"])[:200]}' for x in rows)
        + f'\n\n可选情绪：{"/".join(EMOTIONS)}。严格只输出一行 JSON。'
    )
    try:
        from agent_world.drama_demo.core.runner.kernel import llm_request_extras

        client, llm_cfg = _client_and_cfg()
        resp = client.chat.completions.create(
            model=llm_cfg.get("model", "deepseek-chat"),
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            temperature=0,
            **llm_request_extras(llm_cfg),
        )
        data = _parse_json(resp.choices[0].message.content or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("emotion judge LLM failed: %s", exc)
        return {}

    out: Dict[str, str] = {}
    for e in (data.get("emotions") or []):
        try:
            out[str(e.get("id"))] = normalize_emotion(e.get("emotion"))
        except Exception:  # noqa: BLE001
            continue
    return out
