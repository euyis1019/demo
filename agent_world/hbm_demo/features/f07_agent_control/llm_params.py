"""F07 L2 — resolve temperature / max_tokens from turn_control.yaml."""

from __future__ import annotations

from typing import Any, Dict

from agent_world.hbm_demo.features.f07_agent_control.config import load_turn_control


def resolve_llm_params(phase: str, player_turn: int) -> Dict[str, Any]:
    """Return ``{temperature, max_tokens}`` for the given phase / turn."""
    cfg = load_turn_control()
    table = cfg.get("llm_params") or {}
    if phase == "Phase 3" and player_turn >= 16:
        block = table.get("Phase 3_turn16") or table.get("Phase 3") or {}
    else:
        block = table.get(phase) or table.get("Phase 1") or {}
    return {
        "temperature": float(block.get("temperature", 0.65)),
        "max_tokens": int(block.get("max_tokens", 500)),
    }


def resolve_passive_llm_params(phase: str) -> Dict[str, Any] | None:
    """Lower temperature for Phase 1 passive exec ticks (dev_logs/29 E4)."""
    cfg = load_turn_control()
    table = cfg.get("llm_params") or {}
    key = "Phase_1_passive" if phase == "Phase 1" else f"{phase.replace(' ', '_')}_passive"
    block = table.get(key)
    if not isinstance(block, dict) or not block:
        return None
    return {
        "temperature": float(block.get("temperature", 0.35)),
        "max_tokens": int(block.get("max_tokens", 120)),
    }
