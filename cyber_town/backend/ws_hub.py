"""WebSocket 连接管理：注册/广播/玩家命令入队（方案 §6）。

协议（统一信封）：
* 下行：``{"type": "hello_ack"|"snapshot"|"ack"|"error", ...}``
* 上行：``{"action": str, "client_seq": int, "kwargs": dict}``

上行命令经 ``PlayerAgent.push_command`` 白名单校验后入队；非法命令回
error 帧（错误码见方案 §6.2），合法命令回 ack 帧（仅表示「已入世界队列」，
NPC 反应要等下一拍快照）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)


class WSHub:
    """单世界多连接的 WS 集线器（本期单玩家，多连接=同一玩家多视图）。"""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def register(self, ws: WebSocket, hello: Dict[str, Any]) -> None:
        """accept + 发 hello 握手帧 + 纳入广播列表。"""
        await ws.accept()
        await ws.send_json(hello)
        self._clients.add(ws)
        log.info("WS 连接接入，当前 %d 个", len(self._clients))

    def unregister(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        log.info("WS 连接断开，当前 %d 个", len(self._clients))

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        """向所有连接推送；发送失败的连接就地移除（fail-soft）。

        注：当前为顺序发送（单玩家本机场景，慢客户端风险可被变速拍吸收，
        见 tick_loop 契约）；多人/远程阶段再升级为 gather + per-send 超时
        （方案 §14 多人扩展 todo）。
        """
        dead: List[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 — 单连接故障不阻断他人
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)

    async def handle_client(self, ws: WebSocket, player: Any) -> None:
        """单连接收包循环：校验 → 入队 → ack/error。直到断开。"""
        try:
            while True:
                try:
                    msg = await ws.receive_json()
                except ValueError:
                    await self._send_error(ws, None, "BAD_REQUEST", "非 JSON 消息")
                    continue
                client_seq = msg.get("client_seq")
                command = {
                    "action": msg.get("action"),
                    "kwargs": msg.get("kwargs") or {},
                }
                if player.push_command(command):
                    await ws.send_json(
                        {"type": "ack", "data": {"client_seq": client_seq}}
                    )
                else:
                    await self._send_error(
                        ws, client_seq, "UNKNOWN_COMMAND",
                        f"非法命令：{command['action']!r}（未知 action 或缺参数）",
                    )
        except WebSocketDisconnect:
            pass
        finally:
            self.unregister(ws)

    @staticmethod
    async def _send_error(
        ws: WebSocket, client_seq: Any, code: str, message: str,
    ) -> None:
        try:
            await ws.send_json({
                "type": "error",
                "data": {"client_seq": client_seq, "code": code, "message": message},
            })
        except Exception:  # noqa: BLE001
            pass
