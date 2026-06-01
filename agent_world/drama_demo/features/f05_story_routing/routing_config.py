"""F05 路由开关 + 群聊门控关键词。

剧情推进已由 LLM 导演(director.py)负责，旧的相位/谈判关键词集合(approve/reject/escort/expel/
phase4_deal/return_to_negotiation 等)与超时兜底已删；这里只剩：路由模式开关、节点(导演)驱动开关、
以及群聊门控(需求三)用的"同意/拒绝入群"关键词。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import yaml

from agent_world.drama_demo.shared.prompt_paths import routing_config_path

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


def is_story_pack_routing_enabled() -> bool:
    """是否走导演驱动路由（默认开）；DRAMA_STORY_PACK_ROUTING=0 才关。"""
    return os.environ.get("DRAMA_STORY_PACK_ROUTING", "1").strip() not in ("0", "false", "False", "no", "off")
