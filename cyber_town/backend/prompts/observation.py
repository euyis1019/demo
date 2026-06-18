"""NPC user prompt 渲染：观察 → 生活化文本（原 agents/npc.py::_observation_to_text）。

这是发给 NPC 的整段 user 消息——所有「怎么把世界呈现给 LLM」的措辞都在
这里。入口 ``render_observation(npc, obs, t)``，npc 为 CyberTownNPC 鸭子类型
（读 name/agent_id/groups/name_directory/available_places/segment_store/
current_state_set_at/wall_start_time/minutes_per_tick）。

⚠ 两条不可破约定：
1. 「# 当前 tick：t={t}」与「# 你是：agent_id={id}」被 llm/client.py 的
   Mock 正则（_RE_AGENT/_RE_TICK）反解依赖——这两个 token 格式不能动；
2. 收尾【这一拍】是 W3 自主性审计 B4 的产物：中性总括 + 三条纪律，
   不可回退成逐条行为模板（高频重复会累积诱导行为倾向）。
"""

from __future__ import annotations

from typing import Any, Dict, List

# 收尾纪律块（中性总括 + 纪律，怎么过这一拍全归 LLM）
TURN_DISCIPLINE = (
    "【这一拍】按你的人设和眼前情形自然地过——说话、做事、走动、"
    "或者就安静待着（do_nothing），全凭你自己，沉默也完全正常。\n"
    "说话像真人当面唠嗑：**一拍只说一句短话**（十来个字最自然），有来有往、"
    "一句一句地接，别一口气说一长段——把长话拆成好几拍慢慢聊更像活人。\n"
    "其余纪律：别和『你自己最近做过的』雷同（不复读）；"
    "**对方用哪个渠道找你，回的时候就用同一个渠道**——私信(send_message)来的私信回、"
    "群里(send_to_group)说的在群里接、当面(speak_to_local)讲的当面答，"
    "话才会落在对方正盯着的那一页，不会跑到别处他看不见。\n"
    "别人特意发给你的私信**这一拍必须回应、而且用 send_message 回到私聊里**"
    "（哪怕他人就在你跟前——当面喊一嗓子，他盯着私聊页是看不到的，等于白回）——"
    "哪怕那句话冒犯了你、让你不舒服、或是没头没尾的怪话，照样要回：可以生气、"
    "回怼、质问、表达莫名其妙，这都是『回应』；唯独不许装没看见。"
    "怎么答、答什么、用什么语气，全由你。"
)

# W7：私信渲染收尾的回应提醒（追加在私信清单之后，仅有私信时出现）
# W17：明确「用 send_message 回」——同地点时若用 speak_to_local 回，话进的是
# 玩家『当面说』页而非『私聊』页，玩家盯着私聊页看不到=体感「已读不回」。
DM_RESPONSE_NOTE = (
    "  ↑ 以上私信是对方专门私下发给你的，正在『私聊』里等你回音。这一拍就回，"
    "而且**回私信要用 send_message**（哪怕他人就在你跟前——你当面喊一嗓子，"
    "他盯着私聊页是看不到的，等于没回）；内容再难听、再奇怪，也用你自己的方式"
    "回它一句。不回应=已读不回，街坊间最伤人的做法。"
)

# W17：群消息渲染收尾的接话引导（追加在群消息清单之后，仅有群消息时出现）。
# 软引导：有想说才接、可以不接；只是把『群里冷场没人应』的社交尴尬摆出来。
GROUP_CHIME_NOTE = (
    "  ↑ 群里有人喊话/搭话，街坊们一般都会随口接一句（哪怕就一句『在呢』"
    "『咋啦』『晚上行啊』）——想接就用 send_to_group 回到群里，别让人对着空群"
    "干等；手头实在脱不开身，也可以这拍先不接。"
)


def _label(npc: Any, agent_id: Any) -> str:
    """agent_id → 『名字(agent_N)』显示标签。"""
    try:
        aid = int(agent_id)
    except (TypeError, ValueError):
        return str(agent_id)
    name = npc.name_directory.get(aid)
    return f"{name}(agent_{aid})" if name else f"agent_{aid}"


def _wall_clock_label(npc: Any, t: int) -> str:
    """tick → 'HH:MM'（解析失败返回空串，提示词优雅降级）。"""
    try:
        h, m = npc.wall_start_time.split(":")
        base_min = int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return ""
    total = (base_min + int(t) * int(npc.minutes_per_tick)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _recent_self_actions(npc: Any, limit: int = 4) -> List[Dict[str, Any]]:
    """从 segment_store 读自己最近的动作（防 loop 的关键上下文）。"""
    if npc.segment_store is None:
        return []
    try:
        entries = npc.segment_store.get(npc.agent_id) or []
    except Exception:  # noqa: BLE001
        return []
    out: List[Dict[str, Any]] = []
    for e in entries[-limit:]:
        kind = getattr(e, "kind", "")
        payload = getattr(e, "payload", {}) or {}
        t_e = getattr(e, "t", "?")
        if kind == "speak_to_local":
            summary = f"当面说：{payload.get('content', '')}"
        elif kind == "send_message":
            summary = f"私信 {_label(npc, payload.get('target'))}：{payload.get('content', '')}"
        elif kind == "send_to_group":
            summary = f"群聊(g{payload.get('group_id')})：{payload.get('content', '')}"
        elif kind == "request_move":
            summary = f"动身去 {payload.get('place_id')}"
        elif kind == "update_state":
            summary = f"状态：{payload.get('new_state', '')}"
        elif kind == "update_short_term_goal":
            summary = f"小目标：{payload.get('new_goal', '')}"
        elif kind == "do_nothing":
            summary = "发呆/干自己的活"
        else:
            summary = f"{kind} {payload}"
        out.append({"t": t_e, "summary": summary[:160]})
    return out


def render_observation(npc: Any, obs: Any, t: int) -> str:
    """观察 → user prompt 全文（生活化版）。"""
    lines: List[str] = []
    wall = _wall_clock_label(npc, t)
    wall_tag = f" 世界时间 {wall}" if wall else ""
    lines.append(f"# 当前 tick：t={t}{wall_tag}（每拍约 {npc.minutes_per_tick} 分钟）")

    # 状态陈旧软提醒（无硬性强制——农场慢节奏）
    stale = int(t) - int(getattr(npc, "current_state_set_at", 0) or 0)
    if stale >= 6:
        lines.append(
            f"# ⚠ 你的『当前状态』已 {stale} 拍没更新，若手头的事/位置/心境"
            "已变化，找机会 update_state 写一句新的。"
        )

    lines.append(f"# 你是：agent_id={npc.agent_id}（{npc.name}）")
    lines.append(f"# 你现在的位置：{obs.self_location}")

    briefs = list(getattr(obs, "available_places_brief", []) or [])
    if briefs:
        lines.append("# 可以走去的其他地点（request_move，严格用以下 place_id）：")
        for b in briefs:
            summary = (getattr(b, "summary", "") or "").strip()
            tail = f" —— {summary}" if summary else ""
            lines.append(f"  - {b.place_id}{tail}")
            occupants = getattr(b, "occupants", None)
            if occupants:
                occ = "、".join(_label(npc, o) for o in occupants)
                lines.append(f"    现在在那儿的人：{occ}")
    elif npc.available_places:
        others = [p for p in npc.available_places if p != obs.self_location]
        if others:
            lines.append("# 可以走去的其他地点：" + "、".join(others))

    co = list(obs.co_located_agents or [])
    if co:
        lines.append(
            "# 同地点的人（speak_to_local 当面说话他们都听见）："
            + "、".join(_label(npc, a) for a in co)
        )
    else:
        lines.append("# 同地点的人：没人——当面说话没人听见，自己干自己的就好")

    arrivals = list(getattr(obs, "recent_arrivals", []) or [])
    departures = list(getattr(obs, "recent_departures", []) or [])
    if arrivals:
        lines.append("# 刚走进来：" + "、".join(_label(npc, a) for a in arrivals))
    if departures:
        lines.append("# 刚离开：" + "、".join(_label(npc, a) for a in departures))

    if obs.contacts:
        cs = []
        for c in obs.contacts:
            reach = "可达" if c.can_reach_now else "不可达"
            rels = list(getattr(c, "relation_types", []) or [])
            rel = "、".join(rels) if rels else "认识"
            cs.append(f"{_label(npc, c.agent_id)}[{rel}|{reach}]")
        lines.append("# 你的联系人（send_message 发私信）：" + "、".join(cs))

    if npc.groups:
        lines.append("# 你所在的群（send_to_group 在群里说话）：")
        for g in npc.groups:
            lines.append(
                f"  - group_id={g['group_id']} 名称={g.get('name')!r} "
                f"成员={g.get('members', [])}"
            )

    if obs.incoming_messages:
        # W4：私信与群聊分开渲染——私信是「对方特意私下发给你的话」，
        # 混在消息堆里会被忽略（实测 flash 看见了也不回）。这里只做
        # 事实与社交常识的呈现（私信通常盼着回音），回不回仍由你决定。
        dms = [m for m in obs.incoming_messages
               if getattr(m, "channel_type", "") == "RDC"]
        grp = [m for m in obs.incoming_messages
               if getattr(m, "channel_type", "") == "GRP"]
        others = [m for m in obs.incoming_messages
                  if m not in dms and m not in grp]
        if dms:
            lines.append(
                "# 📨 你收到的私信（对方特意私下发给你、还没得到你的回应——"
                "正等你的回音）："
            )
            for m in dms:
                sender = getattr(m, "sender_id", None)
                lines.append(
                    f"  - {_label(npc, sender)} 私下对你说："
                    f"「{getattr(m, 'content', '')}」（用 send_message 回他）"
                )
            lines.append(DM_RESPONSE_NOTE)
        if grp:
            # W17：群消息单列成醒目板块（原先混在「其他消息」里、零引导→没人接）。
            lines.append("# 💬 群里的消息（镇民群，全群都看得见）：")
            for m in grp:
                gid = getattr(m, "group_id", None)
                lines.append(
                    f"  - 群(g{gid}) {_label(npc, getattr(m, 'sender_id', None))} 说："
                    f"「{getattr(m, 'content', '')}」"
                )
            lines.append(GROUP_CHIME_NOTE)
        if others:
            lines.append("# 你收到的其他消息：")
            for m in others:
                ch = getattr(m, "channel_type", "?")
                gid = getattr(m, "group_id", None)
                tag = ch + (f"#g{gid}" if gid else "")
                lines.append(
                    f"  - [{tag}] 来自 {_label(npc, getattr(m, 'sender_id', None))}："
                    f"{getattr(m, 'content', '')}"
                )

    f2f_history = list(getattr(obs, "f2f_local_history", []) or [])
    if f2f_history:
        current_here = set(obs.co_located_agents or []) | {npc.agent_id}
        lines.append("# 本地最近的当面对话（按时间序，含你自己说过的）：")
        for at_t, sender, _mid, content in f2f_history:
            tag = "" if sender in current_here else "[已离开]"
            lines.append(f"  - t={at_t} {_label(npc, sender)}{tag}：{content}")

    if obs.overheard:
        lines.append("# 你旁听到的（不是说给你的，但你在场）：")
        for o in obs.overheard:
            lines.append(f"  - {getattr(o, 'content', '')}")

    if obs.recent_failed_attempts:
        lines.append(
            f"# 上一拍你有 {len(obs.recent_failed_attempts)} 条消息没送到"
            "（对方不可达）。"
        )

    if obs.group_events:
        lines.append("# 群里的动静：")
        for ge in obs.group_events:
            lines.append(
                f"  - {getattr(ge, 'event_type', '?')} "
                f"{_label(npc, getattr(ge, 'agent_id', '?'))} "
                f"在 group_{getattr(ge, 'group_id', '?')}"
            )

    my_recent = _recent_self_actions(npc, limit=4)
    if my_recent:
        lines.append("# 你自己最近做过的（别车轱辘重复同样的话/动作）：")
        for entry in my_recent:
            lines.append(f"  - t={entry['t']} {entry['summary']}")

    lines.append("")
    lines.append(TURN_DISCIPLINE)
    return "\n".join(lines)
