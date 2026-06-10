"""PlayerAgent —— 人类驱动的虚拟农夫（不调 LLM）。

满足引擎对 agent 的 duck-type 契约（world/step.py::_decide /
_extract_actions）：提供与 NPC 同形的字段 + ``perform_action_by_llm``。
每拍从 ``command_queue`` 非阻塞取**一条**玩家命令翻译成动作；队列空则
do_nothing。玩家动作与 NPC 动作走同一条 dispatcher 路径，等权注入世界。

M0 阶段命令由 CLI 注入；M1 起由 WebSocket 入队（接口不变）。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cyber_town.backend.actions import (
    AgentResponse,
    ToolCall,
    do_nothing_response,
    make_response,
)

log = logging.getLogger(__name__)

# 玩家可用动作白名单：action -> 必填参数名集合（对齐 dispatcher._route 的 kwargs）
_ALLOWED_ACTIONS: Dict[str, Tuple[str, ...]] = {
    "speak_to_local": ("content",),
    "send_message": ("target", "content"),
    "send_to_group": ("group_id", "content"),
    "request_move": ("place_id",),
    "do_nothing": (),
}


@dataclass
class PlayerAgent:
    """世界里的玩家实体：字段佯装成 NPC，行为由命令队列驱动。"""

    agent_id: int
    name: str = "农场主"
    # ---- 引擎/感知层会读到的 duck-type 字段（哪怕空串也要有）----
    soul: str = ""
    long_term_goal: str = ""
    current_state: str = ""
    current_state_set_at: int = 0
    short_term_goal: str = ""
    last_message_seen_at: int = -1
    # 群成员信息须预填——_seed_world 只写 DB，agent 对象字段不会自动同步
    groups: List[Dict[str, Any]] = field(default_factory=list)

    # ---- 玩家命令队列（WS/CLI 入队，世界拍出队）----
    command_queue: "asyncio.Queue[Dict[str, Any]]" = field(
        default_factory=asyncio.Queue
    )

    def push_command(self, command: Dict[str, Any]) -> bool:
        """入队一条玩家命令 ``{"action": str, "kwargs": dict}``。

        Returns:
            False 表示命令不合法（未知 action / 缺参数），已拒绝入队。
        """
        ok, reason = self._validate(command)
        if not ok:
            log.warning("拒绝玩家命令 %s：%s", command, reason)
            return False
        self.command_queue.put_nowait(command)
        return True

    async def perform_action_by_llm(self, world: Any, t: int) -> AgentResponse:
        """一拍出队一条命令；队列空 → do_nothing（不卡 tick、零 LLM）。"""
        try:
            cmd = self.command_queue.get_nowait()
        except asyncio.QueueEmpty:
            return do_nothing_response()
        action = str(cmd.get("action", "do_nothing"))
        kwargs = dict(cmd.get("kwargs") or {})
        log.info("玩家动作 t=%s：%s %s", t, action, kwargs)
        return make_response([ToolCall(tool_name=action, args=kwargs)])

    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate(command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        action = str(command.get("action", ""))
        required = _ALLOWED_ACTIONS.get(action)
        if required is None:
            return False, f"未知 action：{action!r}"
        kwargs = command.get("kwargs") or {}
        missing = [k for k in required if k not in kwargs]
        if missing:
            return False, f"{action} 缺参数：{missing}"
        return True, None
