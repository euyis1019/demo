"""F07 L4 — assemble shared Story Bible + agent overlay + turn hints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.hbm_demo.features.f07_agent_control.config import recap_window_ticks


def _agent_label(agent_id: int, name_map: Dict[int, str]) -> str:
    if int(agent_id) == 0:
        return "玩家"
    return str(name_map.get(int(agent_id)) or f"Agent{agent_id}")


def _short_quote(content: str, limit: int = 48) -> str:
    text = " ".join(str(content or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_thread_recap(
    agent_id: int,
    t: int,
    world_db: Any,
    name_map: Dict[int, str],
    *,
    window: Optional[int] = None,
) -> str:
    """Read-only recent dialogue/OS summary for L4 (dev_logs/31 §6.3)."""
    if world_db is None:
        return ""

    win = int(window) if window is not None else recap_window_ticks()
    since_t = max(0, int(t) - win)
    t_now = int(t)
    aid = int(agent_id)

    lines: List[str] = []
    seen_utterances: set[tuple[Any, ...]] = set()
    try:
        rows = world_db.fetch_messages_for_recap(since_t, t_now, limit=40)
    except Exception:
        rows = []

    for row in rows:
        ch = str(row.get("channel_type") or "")
        at_tick = int(row.get("attempted_at") or 0)
        sender_id = row.get("sender_id")
        content = _short_quote(str(row.get("content") or ""))
        if not content or sender_id is None:
            continue
        sid = int(sender_id)
        dedupe_key = (
            ch,
            at_tick,
            sid,
            str(row.get("place_id") or ""),
            int(row.get("recipient_id") or 0) if ch == "RDC" else int(row.get("group_id") or 0),
            content,
        )
        if dedupe_key in seen_utterances:
            continue
        seen_utterances.add(dedupe_key)

        if ch == "F2F":
            place = str(row.get("place_id") or "room")
            if sid == aid:
                lines.append(f"- 你(F2F@{place}, t={at_tick}): 「{content}」")
            else:
                lines.append(
                    f"- {_agent_label(sid, name_map)}→你(F2F@{place}, t={at_tick}): 「{content}」"
                    if row.get("place_id")
                    else f"- {_agent_label(sid, name_map)}(F2F, t={at_tick}): 「{content}」"
                )
        elif ch == "RDC":
            recipient_id = row.get("recipient_id")
            if recipient_id is None:
                continue
            rid = int(recipient_id)
            if sid != aid and rid != aid:
                lines.append(
                    f"- {_agent_label(sid, name_map)}→{_agent_label(rid, name_map)}"
                    f"(RDC, t={at_tick}): 「{content}」"
                )
            elif sid == aid:
                lines.append(
                    f"- 你→{_agent_label(rid, name_map)}(RDC, t={at_tick}): 「{content}」"
                )
            else:
                lines.append(
                    f"- {_agent_label(sid, name_map)}→你(RDC, t={at_tick}): 「{content}」"
                )
        elif ch == "GRP":
            group_id = row.get("group_id")
            if sid == aid:
                lines.append(f"- 你(GRP#{group_id}, t={at_tick}): 「{content}」")
            else:
                lines.append(
                    f"- {_agent_label(sid, name_map)}(GRP#{group_id}, t={at_tick}): 「{content}」"
                )

    os_lines: List[str] = []
    try:
        state_rows = world_db.fetch_state_logs_since(since_t, t_now, agent_id=aid)
    except Exception:
        state_rows = []
    for row in state_rows[-5:]:
        os_lines.append(
            f"- update_state @ t={int(row['at_tick'])}: 「{_short_quote(str(row.get('content') or ''))}」"
        )

    sections: List[str] = []
    if lines:
        sections.append("【近期对话摘要】\n" + "\n".join(lines[-12:]))
    if os_lines:
        sections.append("【你最近 OS】\n" + "\n".join(os_lines))
    return "\n\n".join(sections)


def _section(title: str, body: Optional[str]) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    return f"【{title}】\n{text}"


def _use_pack_knowledge() -> bool:
    """agent 知识块一律从活跃 Story Pack 数据驱动生成（黄仁勋旧 abcs 文案已退役）。"""
    return True


def _pack_agent(pack: Any, agent_id: int) -> Dict[str, Any]:
    for a in pack.agents.get("agents") or []:
        if int(a.get("agent_id", -1)) == int(agent_id):
            return a
    return {}


def _pack_name(pack: Any, agent_id: int) -> str:
    return str(_pack_agent(pack, agent_id).get("name") or f"Agent{agent_id}")


def _pack_relations_for(pack: Any, agent_id: int) -> str:
    rels = pack.relations.get("relations") if isinstance(pack.relations, dict) else (pack.relations or [])
    lines: List[str] = []
    for r in rels or []:
        src, dst, rtype = int(r.get("src", -1)), int(r.get("dst", -1)), str(r.get("type", ""))
        sym = bool(r.get("symmetric", False))
        if src == agent_id:
            lines.append(f"- 你对{_pack_name(pack, dst)}：{rtype}")
        elif dst == agent_id:
            lines.append(
                f"- 你与{_pack_name(pack, src)}：{rtype}" if sym
                else f"- {_pack_name(pack, src)}对你：{rtype}"
            )
    return "\n".join(lines)


def _pack_place_scene(pack: Any, place_id: str) -> str:
    for p in pack.places.get("places") or []:
        if p.get("place_id") == place_id:
            attrs = p.get("attrs") or {}
            return ". ".join(s for s in (attrs.get("summary"), attrs.get("behavior_hint")) if s)
    return ""


def build_pack_agent_knowledge(
    session: Any,
    agent_id: int,
    player_text: str,
    *,
    channel: str,
) -> str:
    """数据驱动的 agent 知识块：人设/目标/当前幕场景/关系 全部从活跃 Story Pack 读，
    无任何 HBM/黄仁勋写死文案。换 Story Pack 即换角色与剧情。"""
    from agent_world.hbm_demo.shared import story_config

    pack = story_config.active_pack()
    aid = int(agent_id)
    a = _pack_agent(pack, aid)
    name = str(a.get("name") or f"Agent{aid}")

    node_id = getattr(session, "current_node_id", None) or pack.graph.initial_node
    node = pack.graph.nodes.get(node_id)
    place_id = node.place_focus if node else str(getattr(session, "place_id", ""))

    # 1) 你是谁——人设尽量厚：身份/性格/说话风格/目标/此刻状态
    who = f"你是{name}（{a.get('role', '')}{('·' + a.get('faction', '')) if a.get('faction') else ''}）。{a.get('soul', '')}"
    if a.get("speech_style"):
        who += f"\n说话风格：{a['speech_style']}"
    samples = a.get("speech_samples") or []
    if isinstance(samples, list) and samples:
        who += "\n你平时的口吻（范例，模仿这种语气节奏，不要照抄原话）：\n" + "\n".join(
            f"· {s}" for s in samples[:3] if s)
    who += f"\n长期目标：{a.get('long_term_goal', '') or '（随机应变）'}"
    if a.get("current_state"):
        who += f"\n此刻状态：{a['current_state']}"
    sections: List[str] = [_section("你是谁", who)]

    # 2) 你的内心戏——秘密/真实动机/顾忌（不可对玩家明说，但左右你的言行）
    if a.get("inner"):
        sections.append(_section("你的内心（不可明说，但支配你的言行）", str(a["inner"])))

    # 3) 当前这一幕——情境 + 概要
    if node:
        cur = f"{node.beats_label}：{node.summary or ''}"
        if node.scene_brief:
            cur += f"\n此刻情境：{node.scene_brief}"
        sections.append(_section("当前这一幕", cur))

    # 4) 你这一幕要怎么演——针对本幕、本角色的具体表演指引（最关键，决定是否贴剧情）
    direction = node.directions.get(aid) if node else None
    if direction:
        sections.append(_section("你这一幕要做的", direction))

    # 5) 所在场景 + 关系
    scene = _pack_place_scene(pack, place_id)
    if scene:
        sections.append(_section("所在场景", scene))
    rels = _pack_relations_for(pack, aid)
    if rels:
        sections.append(_section("你与在场/相关之人的关系", rels))

    # 6) 玩家互动 + 留在角色里的硬性要求
    if channel == "inject":
        sections.append(_section(
            "玩家刚对你说",
            f"「{player_text}」\n请以{name}的身份、口语化地当面回应玩家（用 speak_to_local 说 1–4 句短话）。"
            f"先接住玩家这一句的具体内容/情绪、据此回应，再带出你的目的——不要无视玩家、不要把话题硬拉回预设台词。"
            f"贴合你的性格、说话风格、内心动机与「你这一幕要做的」。情绪强烈时用神态/动作/语气/反问来表现"
            f"（show，别直接说「我很生气」这种白话）；藏着秘密就用旁敲侧击、客套、回避去演，别直白说破。",
        ))
    elif channel == "opening":
        opening = a.get("opening_line")
        if opening:
            sections.append(_section(
                "开场",
                f"用接近这句口吻的话开场：「{opening}」——可微调以贴合此刻处境，自然引出当前这一幕。"))
        else:
            sections.append(_section(
                "开场", f"用 1–2 句符合{name}身份、说话风格与此刻处境的话开场，自然引出当前这一幕。"))
    else:
        sections.append(_section(
            "此刻",
            f"现在没有人正对你说话。先想一想：你{name}此刻是否真有话要说、或有事要做"
            f"（回应刚发生的事、找某人、推进你的目的/内心图谋）？"
            f"——确有必要才以{name}的身份开口或行动；否则就静观其变、do_nothing，别硬找话说、别没事刷存在感。"
            f"始终留在角色里。"))

    # 始终钉一条硬性反 OOC 规则在末尾（防长对话漂移/破戏）
    sections.append(_section(
        "始终遵守",
        f"你就是{name}本人，只说/做此刻{name}会说会做的。绝不跳出角色、不复述人设、不提你是 AI 或在演戏、"
        f"不替玩家做决定、不替别的角色发言。",
    ))
    return "\n\n".join(s for s in sections if s)


def build_agent_knowledge(
    session: Any,
    agent_id: int,
    player_text: str,
    *,
    channel: str,
) -> str:
    """从活跃 Story Pack 数据驱动组装 agent L4 知识块。channel: ``inject`` | ``notification`` | ``opening``。"""
    return build_pack_agent_knowledge(session, agent_id, player_text, channel=channel)


def build_notification_snippet(session: Any, agent_id: int) -> str:
    return build_agent_knowledge(
        session,
        agent_id,
        player_text="",
        channel="notification",
    )
