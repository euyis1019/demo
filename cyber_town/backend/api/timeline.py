"""agent 行为时间线（M6 档案页后端）：一个 agent 的可观察人生流水。

数据源归并（避免重复）：
* **SegmentStore**（引擎内存近况）→ 非消息类动作：OS（update_state）、
  移动（request_move）、小目标（update_short_term_goal）；
  消息类（speak/send/group）跳过——由 DB 统一供给（才有双向+对方名）。
* **direct_message 表** → 双向消息：当面说（F2F 扇出按内容折叠）/
  私信收发 / 群聊收发。

输出条目：``{t, time, type, text}``，time 为世界时间 HH:MM（后端换算，
前端零时钟逻辑）。type ∈ {os, move, goal, speak, heard, dm_out, dm_in,
grp_out, grp_in}。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

log = logging.getLogger(__name__)


def build_timeline(asm: Any, agent_id: int, limit: int = 60) -> List[Dict[str, Any]]:
    """构建某 agent 的行为时间线（按 t 升序，尾部截断到 limit 条）。"""
    agent_id = int(agent_id)
    names = asm.name_directory
    clock_cfg = (asm.scenario.get("clock") or {})
    wall_start = str(clock_cfg.get("start_time", "08:00"))
    mpt = int(clock_cfg.get("minutes_per_tick", 5))

    entries: List[Dict[str, Any]] = []

    # ---- 非消息动作（SegmentStore，内存近况）-------------------------------
    try:
        raw = asm.segment_store.get(agent_id) or []
    except Exception:  # noqa: BLE001
        raw = []
    for e in raw:
        kind = getattr(e, "kind", "")
        p = getattr(e, "payload", {}) or {}
        t = int(getattr(e, "t", 0))
        if kind == "update_state":
            entries.append(_entry(t, "os", f"💭 {p.get('new_state', '')}", wall_start, mpt))
        elif kind == "request_move":
            place = _place_name(asm, p.get("place_id"))
            entries.append(_entry(t, "move", f"🚶 动身去「{place}」", wall_start, mpt))
        elif kind == "update_short_term_goal":
            entries.append(_entry(t, "goal", f"🎯 打算：{p.get('new_goal', '')}",
                                  wall_start, mpt))
        # speak_to_local / send_message / send_to_group 由 DB 消息统一提供

    # ---- 双向消息（direct_message，持久全量）-------------------------------
    rows = asm.world_db._conn.execute(  # noqa: SLF001 — 只读统计（M1 既有姿势）
        "SELECT sender_id, recipient_id, group_id, channel_type, content, "
        "attempted_at FROM direct_message "
        "WHERE delivered=1 AND (sender_id=? OR recipient_id=?) "
        "ORDER BY message_id",
        (agent_id, agent_id),
    ).fetchall()
    seen_f2f: set = set()
    for sender, recipient, gid, ch, content, t in rows:
        sender = int(sender) if sender is not None else -1
        is_out = sender == agent_id
        other = int(recipient) if is_out else sender
        who = names.get(other, f"agent_{other}")
        if ch == "F2F":
            # 自己发的 F2F 扇出多行（每听众一行）→ 按 (t, 内容) 折叠成一句
            key = (int(t), str(content))
            if is_out:
                if key in seen_f2f:
                    continue
                seen_f2f.add(key)
                entries.append(_entry(int(t), "speak", f"🗣 说：{content}", wall_start, mpt))
            else:
                entries.append(_entry(int(t), "heard",
                                      f"👂 听 {who} 说：{content}", wall_start, mpt))
        elif ch == "RDC":
            text = f"📨 私信 {who}：{content}" if is_out else f"📩 收到 {who} 私信：{content}"
            entries.append(_entry(int(t), "dm_out" if is_out else "dm_in",
                                  text, wall_start, mpt))
        elif ch == "GRP":
            gname = _group_name(asm, gid)
            if is_out:
                # 群发同样按每成员一行扇出 → 折叠
                key = (int(t), f"g{gid}:{content}")
                if key in seen_f2f:
                    continue
                seen_f2f.add(key)
                entries.append(_entry(int(t), "grp_out",
                                      f"👥 在「{gname}」说：{content}", wall_start, mpt))
            else:
                entries.append(_entry(int(t), "grp_in",
                                      f"👥 「{gname}」里 {who} 说：{content}",
                                      wall_start, mpt))

    entries.sort(key=lambda x: x["t"])
    return entries[-int(limit):]


def _entry(t: int, type_: str, text: str, wall_start: str, mpt: int) -> Dict[str, Any]:
    return {"t": t, "time": _wall(t, wall_start, mpt), "type": type_, "text": text}


def _wall(t: int, start: str, mpt: int) -> str:
    try:
        h, m = start.split(":")
        total = (int(h) * 60 + int(m) + t * mpt) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
    except ValueError:
        return ""


def _place_name(asm: Any, place_id: Any) -> str:
    """place_id → 中文地名（种子 display_name 字段，数据驱动；缺省回退 id）。"""
    for pl in asm.scenario.get("places", []) or []:
        if pl.get("place_id") == place_id:
            return str(pl.get("display_name") or place_id)
    return str(place_id)


def _group_name(asm: Any, gid: Any) -> str:
    for g in asm.scenario.get("groups", []) or []:
        if int(g.get("group_id", -1)) == int(gid or -1):
            return str(g.get("name") or f"群{gid}")
    return f"群{gid}"
