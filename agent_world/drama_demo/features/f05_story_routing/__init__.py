"""F05 — 剧情路由：LLM 导演按对话推进剧情 + 玩家台词注入装配（无关键词/相位硬规则）。"""

from agent_world.drama_demo.features.f05_story_routing.routing import (
    build_dialogue_event,
    build_inject_payload,
    format_player_dialogue,
    node_inject_ids,
)
from agent_world.drama_demo.features.f05_story_routing.routing_config import (
    is_story_pack_routing_enabled,
)

__all__ = [
    "build_dialogue_event",
    "build_inject_payload",
    "format_player_dialogue",
    "is_story_pack_routing_enabled",
    "node_inject_ids",
]
