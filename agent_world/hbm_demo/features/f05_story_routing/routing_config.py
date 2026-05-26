"""Load F05 routing.yaml — agent_driven vs legacy_stats."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

_ROUTING_PATH = Path(__file__).resolve().parent / "routing.yaml"


@lru_cache(maxsize=1)
def load_routing_config() -> Dict[str, Any]:
    if not _ROUTING_PATH.is_file():
        return {"mode": "legacy_stats", "stats_display_only": False, "signals": {}}
    with _ROUTING_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    block = data.get("routing") if isinstance(data, dict) else {}
    return dict(block) if isinstance(block, dict) else {}


def routing_mode() -> str:
    return str(load_routing_config().get("mode", "legacy_stats")).strip()


def is_agent_driven() -> bool:
    return routing_mode() == "agent_driven"


def is_legacy_stats() -> bool:
    return not is_agent_driven()


def stats_display_only() -> bool:
    return bool(load_routing_config().get("stats_display_only", False))


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
    return _signal_list("expel_keywords", ("请离场", "谈完了", "出去"))


def escort_keywords() -> Tuple[str, ...]:
    return _signal_list("escort_keywords", ("请跟我来", "这边请"))


def return_to_negotiation_keywords() -> Tuple[str, ...]:
    return _signal_list(
        "return_to_negotiation_keywords",
        ("回谈判室", "回到谈判", "回主谈判", "进去谈", "方案可行", "认可"),
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
