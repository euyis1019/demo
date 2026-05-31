"""F05 路由开关 + 群聊门控关键词。

剧情推进已由 LLM 导演(director.py)负责，旧的相位/谈判关键词集合(approve/reject/escort/expel/
phase4_deal/return_to_negotiation 等)与超时兜底已删；这里只剩：路由模式开关、节点(导演)驱动开关、
以及群聊门控(需求三)用的"同意/拒绝入群"关键词。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Tuple

import yaml

from agent_world.hbm_demo.shared.prompt_paths import routing_config_path

_ROUTING_PATH = routing_config_path()


@lru_cache(maxsize=1)
def load_routing_config() -> Dict[str, Any]:
    if not _ROUTING_PATH.is_file():
        return {"mode": "agent_driven", "signals": {}}
    with _ROUTING_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    block = data.get("routing") if isinstance(data, dict) else {}
    return dict(block) if isinstance(block, dict) else {}


def routing_mode() -> str:
    return str(load_routing_config().get("mode", "agent_driven")).strip()


def is_agent_driven() -> bool:
    return routing_mode() == "agent_driven"


def _signal_list(key: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    signals = load_routing_config().get("signals") or {}
    raw = signals.get(key)
    if isinstance(raw, list):
        out = tuple(str(x).strip() for x in raw if str(x).strip())
        if out:
            return out
    return default


def group_consent_keywords() -> Tuple[str, ...]:
    """NPC 通过 F2F 同意玩家加入其群聊的措辞（群聊门控用，需求三）。"""
    return _signal_list(
        "group_consent_keywords",
        ("同意", "欢迎", "加入", "进群", "拉你进", "带你进", "一起聊", "没问题", "可以进", "算你一个"),
    )


def group_reject_keywords() -> Tuple[str, ...]:
    """NPC 拒绝玩家入群的措辞（优先级高于 consent，避免「不同意」误判为「同意」）。"""
    return _signal_list(
        "group_reject_keywords",
        ("不同意", "不行", "别进", "不欢迎", "拒绝", "不可以", "免谈", "没你的份"),
    )


def is_story_pack_routing_enabled() -> bool:
    """是否走导演驱动路由（默认开）；HBM_STORY_PACK_ROUTING=0 才关。"""
    return os.environ.get("HBM_STORY_PACK_ROUTING", "1").strip() not in ("0", "false", "False", "no", "off")
