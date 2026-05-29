"""F12 shared constants — SBTI clinic room grid and agent roster."""

from __future__ import annotations

HBM_ROOM_PLACES: tuple[str, ...] = (
    "nvidia_reception",
    "jensen_private_room",
    "negotiation_room",
    "openai_hq",
)

HBM_AGENT_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)

ROUTING_WORLD_EVENT_CONTENT: dict[str, str] = {
    "A": "前台把写着你名字的病历夹递过来，Morgen 诊疗室的门自己开了。Phase 2 开始。",
    "B": "Morgen 合上小本本，示意你去诅咒测评间看透明化预览。Phase 3 开始。",
    "C": "收音机、倒计时钟和 SUBJECT-0 退到候诊区，终局诊断只剩你与 Morgen。Phase 4 开始。",
}

PLACE_MUTATION_HINT = "死一般的安静，像刚发完朋友圈没人点赞。"
