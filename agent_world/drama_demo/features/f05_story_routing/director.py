"""LLM 导演：读当前剧情节点 + 本幕真实对话，判断玩家是否已把剧情推向某个走向。

全部交由 LLM 理解剧情与对话来「推进世界、判断世界」——**没有任何关键词 / 信号 / 超时等硬规则**。
每条出边带一句自然语言 `condition`（玩家做到这件事才走那条），导演读对话后裁决 advance / stay。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger("agent_world.drama_demo.f05.director")

_BERT_SYSTEM = (
    "你是一部互动剧的「Bert 导演」。剧情由一组「条件→反应」规则(bert)驱动：每条 bert 描述一个"
    "『玩家条件』(trigger)——玩家做到/说到这件事，就该触发它。\n"
    "下面给你**当前已『上膛』的若干 bert**（每条带 id 与它的玩家条件），以及最近真实发生的对话。\n"
    "判断：玩家在最近的对话里，是否已经做到/表达了其中某一条 bert 的条件？\n"
    "  - 抓玩家的真实意图与造成的效果，不必逐字命中条件措辞；\n"
    "  - 玩家只是闲聊/寒暄/提问/还在试探、没真正做到任何一条 → 不触发（id 留空串）；\n"
    "  - 至多只选**一条**最贴合的；若同时像多条，选条件被满足得最充分的那条。\n"
    "严格只输出一行 JSON："
    '{"triggered":"命中的 bert id 或空串","reason":"一句中文理由"}'
)


def _armed_options(armed: List[Any]) -> str:
    """把已上膛的 bert 列成「id｜玩家条件（｜结局）」清单，给导演判定。"""
    lines: List[str] = []
    for b in armed:
        tail = "（这是结局条件）" if getattr(b, "is_ending", False) else ""
        lines.append(f"- id={b.id}｜条件：{b.trigger}{tail}")
    return "\n".join(lines)


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


def _f2f_rows(db: Any, place: str, since_t: int, t_now: int, *, limit: int = 200):
    try:
        return db.fetch_f2f_history_at(str(place), int(t_now), int(since_t), limit=limit)
    except Exception:  # noqa: BLE001
        return []


def latest_player_tick(db: Any, place: str, since_t: int, t_now: int) -> Optional[int]:
    """本幕里玩家(0)最后一次开口的 tick；无则 None。导演只在有新玩家发言时才判。"""
    ticks = [int(r[0]) for r in _f2f_rows(db, place, since_t, t_now) if int(r[1]) == 0]
    return max(ticks) if ticks else None


def scene_transcript(db: Any, place: str, since_t: int, t_now: int, name_map: Dict[int, str], *, limit: int = 40) -> str:
    lines: List[str] = []
    for at_t, sender_id, _mid, content in _f2f_rows(db, place, since_t, t_now, limit=limit):
        who = "玩家" if int(sender_id) == 0 else str(name_map.get(int(sender_id)) or f"Agent{sender_id}")
        text = " ".join(str(content or "").split())
        if text:
            lines.append(f"{who}：{text}")
    return "\n".join(lines[-limit:])


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def judge_bert_triggers(armed: List[Any], transcript: str, name_map: Dict[int, str]) -> Optional[Dict[str, Any]]:
    """Bert 导演：读「已上膛 bert 的玩家条件」+ 最近真实对话，判玩家是否命中某条 bert 的 trigger。

    返回 {"triggered": bert_id, "reason": str}；无上膛/无命中/出错 → None（本拍不触发任何反应）。
    全交 LLM 理解玩家意图与造成的效果——无关键词/信号/超时等硬规则。
    """
    armed = list(armed or [])
    if not armed:
        return None
    user = (
        "【当前已上膛的 bert（玩家做到其『条件』就触发）】：\n"
        + _armed_options(armed)
        + f"\n\n【最近真实发生的对话】：\n{transcript or '（暂无对话）'}\n\n"
        "判断玩家是否已做到其中某一条 bert 的条件。严格只输出一行 JSON。"
    )
    try:
        from agent_world.drama_demo.core.runner.kernel import llm_request_extras

        client, llm_cfg = _client_and_cfg()
        resp = client.chat.completions.create(
            model=llm_cfg.get("model", "deepseek-chat"),
            messages=[{"role": "system", "content": _BERT_SYSTEM}, {"role": "user", "content": user}],
            temperature=0,
            **llm_request_extras(llm_cfg),
        )
        data = _parse_json(resp.choices[0].message.content or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("bert director judge LLM failed: %s", exc)
        return None

    if not data:
        return None
    triggered = str(data.get("triggered") or "").strip()
    if triggered not in {b.id for b in armed}:
        return None  # 空串或非法 id → 本拍不触发
    log.info("bert 触发：%s（%s）", triggered, data.get("reason"))
    return {"triggered": triggered, "reason": str(data.get("reason") or "")}


_CONSENT_SYSTEM = (
    "你在判断一个 NPC 是否同意/欢迎玩家加入他所在的群聊。读这个 NPC 最近当面对玩家说过的话，"
    "判断他的真实态度：是否明确表示接纳、欢迎、答应让玩家加入（或语义等义的友好接纳）。"
    "只要没有明确接纳就算不同意——不要凭单个词，要读懂整句的真实意思。"
    '严格只输出一行 JSON：{"consent": true或false, "reason": "一句中文理由"}'
)


def judge_group_consent(npc_name: str, npc_lines: List[str]) -> bool:
    """LLM 语义判定该 NPC 是否同意玩家入群（无关键词硬规则）。无对话/出错 → False（保守）。"""
    lines = [str(s).strip() for s in (npc_lines or []) if str(s).strip()]
    if not lines:
        return False
    user = (
        f"NPC：{npc_name}\n他最近当面对玩家说的话：\n"
        + "\n".join(f"- {ln}" for ln in lines[-8:])
        + "\n\n他是否同意/欢迎玩家加入他所在的群聊？"
    )
    try:
        from agent_world.drama_demo.core.runner.kernel import llm_request_extras

        client, llm_cfg = _client_and_cfg()
        resp = client.chat.completions.create(
            model=llm_cfg.get("model", "deepseek-chat"),
            messages=[{"role": "system", "content": _CONSENT_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0,
            **llm_request_extras(llm_cfg),
        )
        data = _parse_json(resp.choices[0].message.content or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("group consent judge LLM failed: %s", exc)
        return False
    return bool(data and data.get("consent") is True)
