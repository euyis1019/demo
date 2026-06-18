"""世界快照构建：每拍把世界状态序列化成 WS 下行 JSON（方案 §6.1）。

关键设计（审计 B-3）：**自管消息游标**——引擎在 step 7 对每个 active agent
每拍无条件把 ``last_message_seen_at`` 推进到 t（step.py:271-275），玩家也
不例外；所以这里不能复用该字段做去重，而是维护独立的 ``_cursor``
（上次快照的 t），用 ``fetch_arrived_for(player, t, last_seen=_cursor)``
取增量。``perception.build`` 只读不写（perception.py:200），可安全复用
它取 contacts 可达性。

读时机契约：必须在 ``run_one_tick()`` 返回**之后**调用（t 已结算完）。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Set

from cyber_town.backend.config import day_phase

log = logging.getLogger(__name__)

TICKS_PER_DAY = 288  # 一天 288 拍（每拍 5 分钟，方案 D17）——纪事按天计


class SnapshotBuilder:
    """有状态快照构建器：持有消息游标与 seq 计数（每世界一个实例）。"""

    def __init__(self, asm: Any, tick_seconds: float = 2.5,
                 affinity_manager: Any = None, world_director: Any = None) -> None:
        self._asm = asm
        self._tick_seconds = float(tick_seconds)
        self._affinity = affinity_manager      # 可选（M4）：None 时快照不含好感度
        self._world_director = world_director  # 可选（W5）：环境事件→前端 HUD
        self._seq = 0
        self._cursor = -1                 # 玩家消息 arrive_at 游标（引擎查询是严格 >）
        self._overhear_cursor = -1        # 旁听 attempted_at 游标（引擎查询是 >=，闭区间！）
        self._failed_seen: Set[int] = set()  # 已报告过的失败 message_id
        self._prev_locations: Dict[int, str] = {}  # 上一帧位置（推导进出场）

        # 小镇纪事（焐心小镇支柱5/进度日子线）：每跨一个时段结算一次，
        # 聚合本时段三人好感增量 + 来访农场的街坊（只读，零强制行为）
        self._digest_phase: Optional[str] = None
        self._digest_baseline: Dict[int, int] = {}   # 时段起点的对玩家好感
        self._digest_visitors: Set[int] = set()       # 本时段来过玩家所在地的 NPC
        self._digest_day: int = 1

        clock_cfg = (asm.scenario.get("clock") or {})
        self._wall_start = str(clock_cfg.get("start_time", "08:00"))
        self._minutes_per_tick = int(clock_cfg.get("minutes_per_tick", 5))
        self._group_names: Dict[int, str] = {
            int(g["group_id"]): str(g.get("name") or f"group_{g['group_id']}")
            for g in (asm.scenario.get("groups") or [])
        }

    # ------------------------------------------------------------------ #

    async def build(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """构建一帧快照。``report`` 来自 ``run_one_tick()`` 的返回。"""
        t = int(report.get("t", 0))
        self._seq += 1

        arrivals, departures = self._diff_locations()
        self._track_visitors(arrivals)
        data: Dict[str, Any] = {
            "world_time": self._wall_clock(t),
            "places": self._places(),
            "agents": self._agents(t),
            "player_view": self._player_view(t),
            "recent_arrivals": arrivals,
            "recent_departures": departures,
            "contacts": await self._contacts(t),
            "moves": self._moves(t),
            "failures": list(report.get("failures", []) or []),
            "daily_digest": self._maybe_daily_digest(t),
        }
        if self._affinity is not None:
            data["affinity"] = self._affinity.snapshot_dict()
        if self._world_director is not None:
            data["world_event"] = self._world_director.current_event(t)
        # 游标推进放在所有查询之后（同一帧内各查询共享旧游标）。
        # 注意两套引擎查询的区间语义不同（审查 B-1）：
        #   fetch_arrived_for  用严格 >  → 游标存 t
        #   fetch_overhear_for 用闭区间 >= → 游标必须存 t+1，否则旁听每帧重复
        self._cursor = t
        self._overhear_cursor = t + 1
        return {"type": "snapshot", "seq": self._seq, "t": t, "data": data}

    def hello(self) -> Dict[str, Any]:
        """连接握手帧：协议版本 / 玩家 id / 地点静态元数据。"""
        asm = self._asm
        places = []
        for p in asm.scenario.get("places", []):
            attrs = p.get("attrs") or {}
            places.append({
                "place_id": p["place_id"],
                "summary": attrs.get("summary", ""),
                "roster_visible": bool(attrs.get("roster_visible", True)),
            })
        return {
            "type": "hello_ack",
            "data": {
                "protocol_version": 1,
                "player_agent_id": asm.player.agent_id,
                "tick_interval_ms": int(self._tick_seconds * 1000),
                "clock": {
                    "start_time": self._wall_start,
                    "minutes_per_tick": self._minutes_per_tick,
                },
                "places": places,
                "agents": {
                    str(aid): name for aid, name in asm.name_directory.items()
                },
                "groups": [
                    {"group_id": g["group_id"], "name": g.get("name"),
                     "members": g.get("members", [])}
                    for g in asm.scenario.get("groups", []) or []
                ],
            },
        }

    # ------------------------------------------------------------------ #
    # 各分片                                                                #
    # ------------------------------------------------------------------ #

    def _wall_clock(self, t: int) -> str:
        try:
            h, m = self._wall_start.split(":")
            base = int(h) * 60 + int(m)
        except ValueError:
            return ""
        total = (base + t * self._minutes_per_tick) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"

    def _places(self) -> Dict[str, Any]:
        asm = self._asm
        out: Dict[str, Any] = {}
        occupants: Dict[str, List[int]] = {}
        for a in asm.all_agents:
            pid = asm.world.location_of(a.agent_id)
            occupants.setdefault(pid, []).append(a.agent_id)
        for p in asm.scenario.get("places", []):
            pid = p["place_id"]
            out[pid] = {"occupants": sorted(occupants.get(pid, []))}
        return out

    def _agents(self, t: int) -> Dict[str, Any]:
        asm = self._asm
        bubbles = self._bubbles(t)
        out: Dict[str, Any] = {}
        for a in asm.all_agents:
            aid = a.agent_id
            entry = {
                "name": a.name,
                "location": asm.world.location_of(aid),
                "is_player": aid == asm.player.agent_id,
                "current_state": (a.current_state or "").strip(),
                "bubble": bubbles.get(aid),
            }
            if self._affinity is not None and aid != asm.player.agent_id:
                entry["affinity_to_player"] = self._affinity.to_player_score(aid)
            out[str(aid)] = entry
        return out

    def _bubbles(self, t: int) -> Dict[int, str]:
        """本拍各 agent 的 speak_to_local 内容（F2F 扇出按发送者折叠）。"""
        rows = self._asm.world_db._conn.execute(  # noqa: SLF001 — 见 M1 待迁移项
            "SELECT DISTINCT sender_id, content FROM direct_message "
            "WHERE channel_type='F2F' AND attempted_at=?",
            (t,),
        ).fetchall()
        return {int(r[0]): str(r[1]) for r in rows if r[0] is not None}

    def _player_view(self, t: int) -> Dict[str, Any]:
        asm = self._asm
        pid = asm.player.agent_id

        arrived = asm.world_db.fetch_arrived_for(pid, t, last_seen=self._cursor)
        incoming, f2f, group = [], [], []
        for m in arrived:
            entry = self._msg_dict(m)
            if m.channel_type == "F2F":
                f2f.append(entry)
            elif m.channel_type == "GRP":
                group.append(entry)
            else:
                incoming.append(entry)

        overheard = [
            {
                "message_id": o.message_id,
                "place_id": o.place_id,
                "sender_id": o.sender_id,
                "content": o.content,
                "attempted_at": o.attempted_at,
            }
            for o in asm.world_db.fetch_overhear_for(
                pid, since=self._overhear_cursor,
            )
        ]

        failed = []
        for m in asm.world_db.fetch_failed_attempts_for(pid, max(t - 1, 0)):
            if m.message_id in self._failed_seen:
                continue
            self._failed_seen.add(m.message_id)
            entry = self._msg_dict(m)
            entry["reason"] = self._failed_reason(m)
            failed.append(entry)

        # fetch_for_agent 的 JOIN 已按「玩家所在群」过滤；每行 agent_id 是
        # 事件主体（谁 join/leave/被 kick），actor_id 是发起者（kick 时不同）。
        # asdict 返回 GroupEventRow 全部字段（含 event_id/actor_id，超集于协议示例）。
        group_events = [
            asdict(ge)
            for ge in asm.world_db.fetch_for_agent(pid, max(t - 1, 0))
        ]

        return {
            "incoming": incoming,
            "f2f": f2f,
            "overheard": overheard,
            "failed": failed,
            "group": group,
            "group_events": group_events,
        }

    def _msg_dict(self, m: Any) -> Dict[str, Any]:
        return {
            "message_id": m.message_id,
            "channel": m.channel_type,
            "sender_id": m.sender_id,
            "recipient_id": m.recipient_id,
            "group_id": m.group_id,
            "group_name": self._group_names.get(m.group_id) if m.group_id else None,
            "content": m.content,
            "place_id": m.place_id,
            "attempted_at": m.attempted_at,
            "arrive_at": m.arrive_at,
        }

    def _failed_reason(self, m: Any) -> str:
        """失败原因推断：复用引擎 perception 的 B9 诊断逻辑（只读）。

        引擎不持久化失败原因（仅 delivered=0），这里按当前世界状态实时
        推断——与失败发生时可能有 1 拍误差，作为前端提示足够。
        """
        try:
            return self._asm.perception._unreachable_reason(  # noqa: SLF001
                self._asm.player.agent_id, int(m.recipient_id),
            )
        except Exception:  # noqa: BLE001
            return "unreachable"

    async def _contacts(self, t: int) -> List[Dict[str, Any]]:
        """玩家联系人可达性：复用 perception.build（只读，不动游标字段）。"""
        asm = self._asm
        try:
            _, obs = await asm.perception.build(asm.player, asm.world, t)
        except Exception as exc:  # noqa: BLE001 — 降级出名册而非全空（审查 PROTO-008）
            log.error("快照 contacts 构建失败 t=%s：%s", t, exc)
            return [
                {"agent_id": aid, "name": name, "can_reach_now": False,
                 "reason": "可达性暂不可知（感知层异常）", "relation_types": []}
                for aid, name in asm.name_directory.items()
                if aid != asm.player.agent_id
            ]
        out = []
        for c in (obs.contacts or []):
            out.append({
                "agent_id": c.agent_id,
                "name": asm.name_directory.get(int(c.agent_id)),
                "can_reach_now": bool(c.can_reach_now),
                "reason": getattr(c, "reason", None),
                "relation_types": list(getattr(c, "relation_types", []) or []),
            })
        return out

    def _diff_locations(self) -> tuple:
        """与上一帧位置对比，推导进出场（首帧不报，仅建立基线）。"""
        asm = self._asm
        current = {a.agent_id: asm.world.location_of(a.agent_id)
                   for a in asm.all_agents}
        arrivals, departures = [], []
        if self._prev_locations:
            for aid, place in current.items():
                old = self._prev_locations.get(aid)
                if old is not None and old != place:
                    arrivals.append({"agent_id": aid, "place_id": place})
                    departures.append({"agent_id": aid, "place_id": old})
        self._prev_locations = current
        return arrivals, departures

    # ------------------------------------------------------------------ #
    # 小镇纪事（只读聚合，零强制行为）                                      #
    # ------------------------------------------------------------------ #

    def _track_visitors(self, arrivals: List[Dict[str, Any]]) -> None:
        """累积本时段「来过玩家所在地」的 NPC（= 来串门/找你）。"""
        asm = self._asm
        pid = asm.player.agent_id
        ploc = asm.world.location_of(pid)
        for a in arrivals:
            aid = int(a.get("agent_id"))
            if aid != pid and a.get("place_id") == ploc:
                self._digest_visitors.add(aid)

    def _maybe_daily_digest(self, t: int) -> Optional[Dict[str, Any]]:
        """跨时段时结算一页「小镇纪事」；同时段内返回 None（首帧只建基线）。"""
        if self._affinity is None:
            return None
        phase = day_phase(self._wall_clock(t))
        if not phase:
            return None
        asm = self._asm
        pid = asm.player.agent_id
        npc_ids = [a.agent_id for a in asm.all_agents if a.agent_id != pid]
        cur = {nid: int(self._affinity.to_player_score(nid) or 0) for nid in npc_ids}

        if self._digest_phase is None:          # 首帧：建立基线，不结算
            self._digest_phase = phase
            self._digest_baseline = cur
            return None
        if phase == self._digest_phase:
            return None

        changes: List[Dict[str, Any]] = []
        for nid in npc_ids:
            delta = cur[nid] - self._digest_baseline.get(nid, cur[nid])
            if delta != 0:
                level, _ = self._affinity.level_of(cur[nid])
                changes.append({
                    "name": asm.name_directory.get(nid, f"agent_{nid}"),
                    "delta": delta, "level": level,
                })
        visitors = sorted(
            asm.name_directory.get(v, f"agent_{v}") for v in self._digest_visitors
        )
        warmth = round(sum(cur.values()) / len(cur)) if cur else 0
        digest = {
            "day": self._digest_day,
            "ended_phase": self._digest_phase,
            "warmth": warmth,
            "changes": changes,
            "visitors": visitors,
        }
        ended = self._digest_phase
        self._digest_phase = phase
        self._digest_baseline = cur
        self._digest_visitors = set()
        if ended == "夜里" and phase == "清晨":
            self._digest_day += 1
        return digest

    def _moves(self, t: int) -> Dict[str, str]:
        rows = self._asm.world_db._conn.execute(  # noqa: SLF001
            "SELECT agent_id, place_id FROM agent_location WHERE arrived_at=?",
            (t,),
        ).fetchall()
        return {str(int(r[0])): str(r[1]) for r in rows}
