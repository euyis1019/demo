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
    "你是一部互动剧情的「导演 / drama manager」。纵观整个故事的走向地图与张力弧，读这一幕的剧情背景、"
    "最近真实发生的对话、以及当前张力值，做两件事：\n"
    "(1) 更新故事张力 tension(0–100)：玩家打探/铺垫/试探时缓升；出现冲突/逼问/反转/揭露/背叛时陡升；"
    "缓和/闲聊/收尾时回落。给出你对此刻整体张力的读数（不必与旧值连续，按剧情实际紧张程度判）。\n"
    "(2) 判断是否推进剧情走向：\n"
    "  - 当对话显示玩家做出/表达了某个走向『条件』所描述的选择或行动——或玩家用别的方式把局势实质地朝"
    "那个走向推进了——就 advance 到那个走向（抓玩家真实意图与造成的效果，不必逐字命中条件措辞）；\n"
    "  - 玩家只是闲聊、寒暄、提问、还在打探、明显犹豫未定 → stay；\n"
    "  - 当张力已高(≥70)、且玩家已把核心冲突推到收束/摊牌，而走向里存在合适的『结局』走向时，优先"
    "advance 到最贴合当前局势的那个结局——结局由故事张力与玩家历程触发，不必死等逐字条件命中。\n"
    "严格只输出一行 JSON："
    '{"decision":"advance或stay","target":"走向id或空串","tension":0到100整数,"reason":"一句中文理由"}'
)


def _story_outline(graph: Any, current_node_id: str) -> str:
    """整张故事走向地图（所有幕 + 结局），标出当前所在幕，给导演全局视野而非只看当前出边。"""
    lines: List[str] = []
    for nid, n in graph.nodes.items():
        mark = "▶现在" if nid == current_node_id else "　"
        lines.append(f"{mark}[{nid}] {n.beats_label}：{n.summary}")
    for eid, e in graph.endings.items():
        lines.append(f"　(结局·{e.kind})[{eid}] {e.summary}")
    return "\n".join(lines)


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


def judge_transition(graph: Any, node_id: str, transcript: str, name_map: Dict[int, str],
                     *, current_tension: int = 0) -> Optional[Dict[str, Any]]:
    """drama-manager 导演：读全局走向 + 本幕对话 + 当前张力，更新张力并判断是否推进。

    返回 {"advance": bool, "target": str, "reason": str, "tension": int}；
    无节点/无可走出边时返回 None（调用方据此不动张力也不推进）。
    """
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
        f"【整个故事的走向地图】（▶ 标出你现在所在的幕）：\n{_story_outline(graph, node_id)}\n\n"
        f"【当前这一幕】{node.beats_label}：{node.summary}\n\n"
        f"【当前故事张力】{int(current_tension)}/100\n\n"
        "【从这一幕可能的走向】（玩家把局势推向对应『条件』所描述的方向时走那条）：\n"
        + "\n".join(f"- id={o['id']}｜条件：{o['condition']}｜走向后：{o['outcome']}" for o in options)
        + f"\n\n【这一幕里最近真实发生的对话】：\n{transcript or '（暂无对话）'}\n\n"
        "结合整张走向地图与当前张力，更新张力并判断玩家是否已把剧情推动到某个走向。严格只输出一行 JSON。"
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

    if not data:
        return None
    try:
        tension = max(0, min(100, int(data.get("tension", current_tension))))
    except (TypeError, ValueError):
        tension = int(current_tension)
    advance = str(data.get("decision")) == "advance"
    target = str(data.get("target") or "")
    if advance and target not in {o["id"] for o in options}:
        advance, target = False, ""
    if advance:
        log.info("director: %s → %s（张力%s｜%s）", node_id, target, tension, data.get("reason"))
    return {"advance": advance, "target": target,
            "reason": str(data.get("reason") or ""), "tension": tension}
