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
    "A": "Jensen 进入私人会议室，Phase 2 开始",
    "B": "Jensen 返回谈判室，Phase 3 开始",
    "C": "CEO 4/5/6 被请至前台，Phase 4 开始",
}

PLACE_MUTATION_HINT = "死一般的寂静，所有人都被 Jensen 带来的底牌震撼了…"
