"""F07 L4 — assemble shared Story Bible + agent overlay + turn hints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_world.drama_demo.features.f07_agent_control.config import recap_window_ticks


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


def _pack_acting_guide(pack: Any) -> str:
    """整段「表演须知」——由设计期管理 agent 按本故事基调生成，存在 Story Pack 的 meta.acting_guide。
    运行期这里只注入、不内嵌任何表演规则（换 Story Pack 即换一套须知）。"""
    meta = getattr(pack, "meta", None) or {}
    return str(meta.get("acting_guide") or "").strip()


def build_pack_agent_knowledge(
    session: Any,
    agent_id: int,
    player_text: str,
    *,
    channel: str,
) -> str:
    """数据驱动的 agent 知识块：人设/目标/当前幕场景/关系 全部从活跃 Story Pack 读，
    无任何 HBM/黄仁勋写死文案。换 Story Pack 即换角色与剧情。"""
    from agent_world.drama_demo.shared import story_config

    pack = story_config.active_pack()
    aid = int(agent_id)
    a = _pack_agent(pack, aid)
    name = str(a.get("name") or f"Agent{aid}")

    # 剧情已无「幕/节点」概念：场景取本角色自身所在地（播种位置），降级用玩家所在地。
    place_id = str(a.get("location") or getattr(session, "place_id", "") or "")

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

    # 3) 你现在的反应——若某条 bert 被触发并指定你来反应，这里注入该反应（剧情反应链的落点）。
    #    这是「条件→反应」机制的运行期出口：玩家做到某 trigger，导演就把对应 reaction 注入到 target。
    reaction = (getattr(session, "bert_reactions", None) or {}).get(str(aid))
    if reaction:
        sections.append(_section(
            "你现在的反应（剧情已触发，贴着这个演出来，不要明说这是被安排的）", str(reaction)))

    # 5) 所在场景 + 关系
    scene = _pack_place_scene(pack, place_id)
    if scene:
        sections.append(_section("所在场景", scene))
    rels = _pack_relations_for(pack, aid)
    if rels:
        sections.append(_section("你与在场/相关之人的关系", rels))

    # 6) 玩家互动 / 此刻处境——只摆**事实**，不在此写表演规则（怎么演由下面的「表演须知」统一指导）。
    if channel == "inject":
        sections.append(_section(
            "玩家刚对你说",
            f"「{player_text}」\n用 speak_to_local 当面回应玩家。"))
    elif channel == "opening":
        opening = a.get("opening_line")
        if opening:
            sections.append(_section(
                "开场", f"用接近这句口吻的话开场：「{opening}」——可微调以贴合此刻处境，自然引出当前这一幕。"))
        else:
            sections.append(_section(
                "开场", f"用 1–2 句符合{name}身份与此刻处境的话开场，自然引出当前这一幕。"))
    else:
        sections.append(_section(
            "此刻",
            "现在没有人正对你说话。按你的处境、目的与内心，自行决定此刻是开口、行动、还是 do_nothing。"))

    # 7) 表演须知——由设计期管理 agent 按本故事基调生成（meta.acting_guide），运行期只注入、不内嵌规则。
    guide = _pack_acting_guide(pack)
    if guide:
        sections.append(_section("表演须知（贴着演，别跳戏）", guide))
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
