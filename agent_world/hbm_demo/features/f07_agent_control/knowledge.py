"""F07 L4 — assemble shared Story Bible + agent overlay + turn hints."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agent_world.hbm_demo.features.f07_agent_control.config import story_knowledge_dir
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
    stats = getattr(session, "stats", None) or {}
    turn = int(getattr(session, "player_turn", 1))
    phase = str(getattr(session, "phase", "Phase 1"))
    vision = stats.get("vision", 0)
    execution = stats.get("execution", 0)
    trust = stats.get("trust", 0)
    burnout = stats.get("burnout", 0)
    node_hint = ""
    if phase == "Phase 1" and turn >= 3:
        node_hint = f"距节点 A（Turn 4，需 Vision+Execution≥15）还有 {max(4 - turn, 0)} Turn。"
    elif phase == "Phase 2" and turn >= 10:
        node_hint = f"距节点 B（Turn 12，需 Execution≥20 + Tech VP 正面 RDC）还有 {max(12 - turn, 0)} Turn。"
    elif phase == "Phase 3" and turn >= 18:
        node_hint = f"距节点 C（Turn 20，需 Burnout<80 且 Vision≥30）还有 {max(20 - turn, 0)} Turn。"
    elif phase == "Phase 4" and turn >= 23:
        node_hint = f"距终局节点 D（Turn 25）还有 {max(25 - turn, 0)} Turn。"
    return (
        f"当前 Turn {turn}，Phase {phase}。"
        f"数值：Vision={vision} Execution={execution} Trust={trust} Burnout={burnout}。"
        f"{node_hint}"
    ).strip()


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
