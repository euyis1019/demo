"""F12 shared constants — HBM demo room grid and agent roster."""

from __future__ import annotations

HBM_ROOM_PLACES: tuple[str, ...] = (
    "nvidia_reception",
    "jensen_private_room",
    "negotiation_room",
    "openai_hq",
)

HBM_AGENT_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)

ROUTING_WORLD_EVENT_CONTENT: dict[str, str] = {
    "A": "前台带你穿过走廊，进入私密会议室。Jensen 推门而入。Phase 2 开始。",
    "B": "Jensen 带你回到主谈判室，气氛为之一变。Phase 3 开始。",
    "C": "三位 CEO 被请离谈判室，终局只剩你与 Jensen（Tech VP 旁听）。Phase 4 开始。",
}

PLACE_MUTATION_HINT = "死一般的寂静，所有人都被 Jensen 带来的底牌震撼了…"
