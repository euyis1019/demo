"""LLM 导演：读当前剧情节点 + 本幕真实对话，判断玩家是否已把剧情推向某个走向。

全部交由 LLM 理解剧情与对话来「推进世界、判断世界」——**没有任何关键词 / 信号 / 超时等硬规则**。
每条出边带一句自然语言 `condition`（玩家做到这件事才走那条），导演读对话后裁决 advance / stay。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger("agent_world.hbm_demo.f05.director")

_SYSTEM = (
    "你是一部互动剧情的「导演」。职责：读这一幕的剧情背景与最近真实发生的对话，判断玩家是否"
    "已经把剧情明确推向某个走向。你不靠任何关键词，只靠对剧情与对话的理解来判断。\n"
    "规则：\n"
    "1. 只有当对话清楚显示玩家做出/表达了某个走向『条件』所描述的选择或行动时，才推进到那个走向；\n"
    "2. 玩家只是闲聊、提问、犹豫、尚未明确选择 → 保持当前幕(stay)；\n"
    "3. 若多个走向都沾边，选最贴合玩家明确意图的那个；拿不准就 stay；\n"
    "4. 严格只输出一行 JSON："
    '{"decision":"advance或stay","target":"走向id或空串","reason":"一句中文理由"}'
)


def _client_and_cfg():
    from openai import OpenAI

    from agent_world.hbm_demo.core.runner.kernel import resolve_api_key
    from agent_world.hbm_demo.shared import story_config

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


def judge_transition(graph: Any, node_id: str, transcript: str, name_map: Dict[int, str]) -> Optional[Dict[str, Any]]:
    """让 LLM 判断从 node_id 出发是否推进、推进到哪条出边的 dst。返回 {"target","reason"} 或 None(=stay)。"""
    node = graph.nodes.get(node_id)
    if node is None:
        return None
    options: List[Dict[str, str]] = []
    for edge, dst in graph.get_children(node_id):
        cond = str(getattr(edge, "condition", "") or "").strip()
        if not cond:
            continue
        if graph.is_ending(dst):
            end = graph.endings.get(dst)
            outcome = f"（结局）{end.summary if end else ''}"
        else:
            nd = graph.nodes.get(dst)
            outcome = nd.summary if nd else ""
        options.append({"id": dst, "condition": cond, "outcome": outcome})
    if not options:
        return None

    user = (
        f"【当前这一幕】{node.beats_label}：{node.summary}\n\n"
        "【可能的走向】（玩家明确做到对应『条件』时才走那条）：\n"
        + "\n".join(f"- id={o['id']}｜条件：{o['condition']}｜走向后：{o['outcome']}" for o in options)
        + f"\n\n【这一幕里最近真实发生的对话】：\n{transcript or '（暂无对话）'}\n\n"
        "判断玩家是否已明确推动到某个走向。严格只输出一行 JSON。"
    )
    try:
        from agent_world.hbm_demo.core.runner.kernel import llm_request_extras

        client, llm_cfg = _client_and_cfg()
        resp = client.chat.completions.create(
            model=llm_cfg.get("model", "deepseek-chat"),
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            temperature=0,
            **llm_request_extras(llm_cfg),
        )
        data = _parse_json(resp.choices[0].message.content or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("director judge LLM failed: %s", exc)
        return None

    if not data or str(data.get("decision")) != "advance":
        return None
    target = str(data.get("target") or "")
    if target not in {o["id"] for o in options}:
        return None
    log.info("director: %s → %s（%s）", node_id, target, data.get("reason"))
    return {"target": target, "reason": str(data.get("reason") or "")}
