"""Load F05 routing.yaml — agent-driven story signals."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from agent_world.hbm_demo.shared.prompt_paths import routing_config_path

_ROUTING_PATH = routing_config_path()


@lru_cache(maxsize=1)
def load_routing_config() -> Dict[str, Any]:
    if not _ROUTING_PATH.is_file():
        return {"mode": "agent_driven", "stats_display_only": True, "signals": {}}
    with _ROUTING_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    block = data.get("routing") if isinstance(data, dict) else {}
    return dict(block) if isinstance(block, dict) else {}


def routing_mode() -> str:
    return str(load_routing_config().get("mode", "agent_driven")).strip()


def is_agent_driven() -> bool:
    return routing_mode() == "agent_driven"


def stats_display_only() -> bool:
    return bool(load_routing_config().get("stats_display_only", True))


def _signal_list(key: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    signals = load_routing_config().get("signals") or {}
    raw = signals.get(key)
    if isinstance(raw, list):
        out = tuple(str(x).strip() for x in raw if str(x).strip())
        if out:
            return out
    return default


def approve_keywords() -> Tuple[str, ...]:
    return _signal_list(
        "approve_keywords",
        ("私人会议室", "私密会议室", "可以见", "带进来", "批准", "这边请", "请跟我来"),
    )


def reject_keywords() -> Tuple[str, ...]:
    return _signal_list("reject_keywords", ("拒绝", "请离开", "保安"))


def expel_keywords() -> Tuple[str, ...]:
    return _signal_list(
        "expel_keywords",
        ("请离场", "谈完了", "出去", "请出去", "你们出去", "先出去", "离场", "谈够了"),
    )


def escort_keywords() -> Tuple[str, ...]:
    return _signal_list("escort_keywords", ("请跟我来", "这边请"))


def return_to_negotiation_keywords() -> Tuple[str, ...]:
    return _signal_list(
        "return_to_negotiation_keywords",
        (
            "回谈判室",
            "回到谈判",
            "回主谈判",
            "进谈判室",
            "去谈判室",
            "跟我进谈判室",
            "方案可行",
            "认可",
        ),
    )


def phase4_deal_keywords() -> Tuple[str, ...]:
    """Broad pre-filter for Phase 4 deal talk — decides only whether to spend an
    LLM conclusion check; intentionally generous (the LLM makes the real call)."""
    return _signal_list(
        "phase4_deal_keywords",
        (
            "offer", "合同", "签字", "入职", "加入", "录用", "入伙", "高管",
            "种子", "融资", "估值", "投资", "期权", "股权", "敲定", "算定",
            "同意", "这么定", "拍桌", "收回", "Distinguished", "DE",
        ),
    )


def require_reception_escort_f2f() -> bool:
    signals = load_routing_config().get("signals") or {}
    return bool(signals.get("require_reception_escort_f2f", False))


def max_turns_phase1_without_approve() -> int:
    signals = load_routing_config().get("signals") or {}
    raw = signals.get("max_turns_phase1_without_approve", 10)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 10


def is_story_advance_enabled() -> bool:
    block = load_routing_config().get("story_advance") or {}
    return bool(block.get("enabled", True))
