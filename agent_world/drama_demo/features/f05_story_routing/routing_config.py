"""F05 路由开关。

剧情推进已由 LLM 导演(director.py)负责，旧的相位/谈判关键词集合与超时兜底、以及读
routing.yaml 的 load_routing_config/routing_mode/is_agent_driven 自循环死链均已删；这里只剩
导演驱动路由的总开关（env 驱动）。
"""

from __future__ import annotations

import os


def is_story_pack_routing_enabled() -> bool:
    """是否走导演驱动路由（默认开）；DRAMA_STORY_PACK_ROUTING=0 才关。"""
    return os.environ.get("DRAMA_STORY_PACK_ROUTING", "1").strip() not in ("0", "false", "False", "no", "off")
