"""F07 L2 — 解析每拍采样参数（temperature/max_tokens），数据驱动、无写死幕名。

优先取当前 Story Pack 的 meta.llm（每个故事自带语气/篇幅取向，由管理 agent 生成）；缺省用通用默认。
旧版按英文幕名(Phase 1..4 / Phase 3_turn16)逐幕写死采样的映射已退役。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_DEFAULT_TEMPERATURE = 0.65
_DEFAULT_MAX_TOKENS = 500


def _story_llm_cfg() -> Dict[str, Any]:
    """当前活跃 Story Pack 的 meta.llm（无活跃包/字段时返回空 dict，不抛错）。"""
    try:
        from agent_world.hbm_demo.shared import story_config

        return dict(story_config.active_pack().meta.get("llm") or {})
    except Exception:  # noqa: BLE001 — 无活跃包/解析失败时走通用默认
        return {}


def resolve_llm_params(phase: str, player_turn: int) -> Dict[str, Any]:  # noqa: ARG001
    """Return ``{temperature, max_tokens}``。来自 Story Pack meta.llm，缺省用通用默认。

    phase/player_turn 仅为兼容旧签名保留，不再据其分流（采样取向是故事级、由 Story Pack 决定）。
    """
    cfg = _story_llm_cfg()
    return {
        "temperature": float(cfg.get("temperature", _DEFAULT_TEMPERATURE)),
        "max_tokens": int(cfg.get("max_tokens", _DEFAULT_MAX_TOKENS)),
    }


def resolve_passive_llm_params(phase: str) -> Optional[Dict[str, Any]]:  # noqa: ARG001
    """被动拍是否单独降温——默认不区分（返回 None，沿用 resolve_llm_params）。

    如某故事要给「背景/被动」拍单独的采样取向，应由 Story Pack meta.llm.passive 提供，而非引擎写死幕名。
    """
    cfg = _story_llm_cfg().get("passive")
    if not isinstance(cfg, dict) or not cfg:
        return None
    return {
        "temperature": float(cfg.get("temperature", 0.35)),
        "max_tokens": int(cfg.get("max_tokens", 120)),
    }
