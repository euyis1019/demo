"""WS 端到端测试：TestClient 连 /ws/world，验证握手/快照流/命令闭环。

用 Mock LLM + 0.05s 快拍，几百毫秒内即可看到玩家命令经世界拍落回快照。
"""

from __future__ import annotations

import time
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from cyber_town.backend.main import create_app


def _make_client(tmp_path) -> TestClient:
    app = create_app(
        mock=True, tick_seconds=0.05, sim_dir=str(tmp_path),
    )
    return TestClient(app)


def _recv_until(ws: Any, pred, deadline_s: float = 8.0) -> Dict[str, Any]:
    """循环收帧直到谓词命中；超时抛 AssertionError。"""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        frame = ws.receive_json()
        if pred(frame):
            return frame
    raise AssertionError("超时未等到目标帧")


def test_healthz_and_ws_stream(tmp_path) -> None:
    with _make_client(tmp_path) as client:
        r = client.get("/healthz")
        assert r.status_code == 200 and r.json()["status"] == "ok"

        with client.websocket_connect("/ws/world") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello_ack"
            assert hello["data"]["player_agent_id"] == 0

            snap = _recv_until(ws, lambda f: f["type"] == "snapshot")
            assert "agents" in snap["data"]
            # 心跳推进：再收一帧，t 必须单调递增
            snap2 = _recv_until(ws, lambda f: f["type"] == "snapshot")
            assert snap2["t"] > snap["t"]


def test_player_command_round_trip(tmp_path) -> None:
    """玩家发 F2F → ack → 下若干拍快照里出现自己的 bubble（命令真进了世界）。"""
    marker = "WS测试：晚上好啊各位"
    with _make_client(tmp_path) as client:
        with client.websocket_connect("/ws/world") as ws:
            ws.receive_json()  # hello
            ws.send_json({
                "action": "speak_to_local", "client_seq": 7,
                "kwargs": {"content": marker},
            })
            ack = _recv_until(ws, lambda f: f["type"] == "ack")
            assert ack["data"]["client_seq"] == 7

            def player_spoke(f: Dict[str, Any]) -> bool:
                if f.get("type") != "snapshot":
                    return False
                bubble = f["data"]["agents"]["0"]["bubble"]
                return bool(bubble and marker in bubble)

            snap = _recv_until(ws, player_spoke)
            assert snap["data"]["agents"]["0"]["is_player"]


def test_invalid_command_gets_error_frame(tmp_path) -> None:
    with _make_client(tmp_path) as client:
        with client.websocket_connect("/ws/world") as ws:
            ws.receive_json()  # hello
            ws.send_json({"action": "hack_world", "client_seq": 9, "kwargs": {}})
            err = _recv_until(ws, lambda f: f["type"] == "error")
            assert err["data"]["code"] == "UNKNOWN_COMMAND"
            assert err["data"]["client_seq"] == 9
