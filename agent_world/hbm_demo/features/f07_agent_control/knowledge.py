"""F07 L4 — assemble shared Story Bible + agent overlay + turn hints."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agent_world.hbm_demo.features.f07_agent_control.config import (
    recap_window_ticks,
    story_knowledge_dir,
)
from agent_world.hbm_demo.features.f07_agent_control.player_response import (
    format_l6_player_directive,
    format_notification_directive,
)

_STORY = story_knowledge_dir()


def _phase_key(phase: str) -> str:
    mapping = {
        "Phase 1": "phase_1",
        "Phase 2": "phase_2",
        "Phase 3": "phase_3",
        "Phase 4": "phase_4",
    }
    return mapping.get(phase, "phase_1")


@lru_cache(maxsize=8)
def _load_yaml(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def load_phase_shared(phase: str) -> Dict[str, Any]:
    return _load_yaml(str(_STORY / "shared" / f"{_phase_key(phase)}.yaml"))


def load_agent_overlay(agent_id: int) -> Dict[str, Any]:
    return _load_yaml(str(_STORY / "agents" / f"agent_{agent_id}.yaml"))


@lru_cache(maxsize=1)
def load_turn_hints() -> Dict[int, str]:
    raw = _load_yaml(str(_STORY / "turn_hints.yaml"))
    hints = raw.get("turns") or raw
    out: Dict[int, str] = {}
    if isinstance(hints, dict):
        for k, v in hints.items():
            try:
                out[int(k)] = str(v).strip()
            except (TypeError, ValueError):
                continue
    return out


def format_session_facts(session: Any) -> str:
    turn = int(getattr(session, "player_turn", 1))
    phase = str(getattr(session, "phase", "Phase 1"))
    return f"当前 Turn {turn}，Phase {phase}。"


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


def build_agent_knowledge(
    session: Any,
    agent_id: int,
    player_text: str,
    *,
    channel: str,
) -> str:
    """Assemble L4 knowledge block. channel: ``inject`` | ``notification``."""
    phase = str(getattr(session, "phase", "Phase 1"))
    player_turn = int(getattr(session, "player_turn", 1))
    shared = load_phase_shared(phase)
    overlay = load_agent_overlay(agent_id)
    phase_block = (overlay.get("phase_overrides") or {}).get(phase) or {}
    turn_hints = load_turn_hints()
    turn_block = turn_hints.get(player_turn, "")

    sections: List[str] = []
    if channel == "inject":
        sections.append(
            format_l6_player_directive(
                agent_id=agent_id,
                phase=phase,
                player_turn=player_turn,
                player_text=player_text,
            )
        )
    else:
        sections.append(
            format_notification_directive(
                phase=phase,
                player_turn=player_turn,
                agent_id=agent_id,
            )
        )

    sections.extend(
        [
            _section(
                "本 Phase 世界态",
                "\n".join(
                    s
                    for s in (
                        shared.get("world_state"),
                        shared.get("scene_atmosphere"),
                    )
                    if s
                ),
            ),
            _section("本 Phase 剧情要点", shared.get("plot_beats")),
            _section(
                "你的角色与目标",
                "\n".join(
                    s
                    for s in (
                        overlay.get("identity"),
                        overlay.get("speech_style"),
                        overlay.get("player_stance"),
                        phase_block.get("role_goal"),
                        phase_block.get("example_lines"),
                        _format_checklist(phase_block.get("response_checklist")),
                    )
                    if s
                ),
            ),
            _section("本 Turn 剧本参考", turn_block),
            _section("关系与术语", overlay.get("relationships")),
            _section(
                "硬性禁止",
                "\n".join(
                    s
                    for s in (
                        shared.get("forbidden_actions"),
                        phase_block.get("forbidden_extra"),
                    )
                    if s
                ),
            ),
            _section("本会话事实", format_session_facts(session)),
        ]
    )
    return "\n\n".join(s for s in sections if s)


def _format_checklist(items: Any) -> str:
    if not items:
        return ""
    if isinstance(items, str):
        return items.strip()
    if isinstance(items, list):
        return "\n".join(f"- {x}" for x in items if x)
    return str(items)


def build_notification_snippet(session: Any, agent_id: int) -> str:
    return build_agent_knowledge(
        session,
        agent_id,
        player_text="",
        channel="notification",
    )
