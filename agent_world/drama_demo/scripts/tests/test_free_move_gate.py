#!/usr/bin/env python3
"""NPC 移动语义门控（解耦后，见 core/runner/drama_dispatcher + f05 interpreter_routing）。

新语义（NPC 自由世界）：
  1) **NPC 自主移动 `request_move` 始终放行**——DramaActionDispatcher 不再吞它，无条件委托父类
     dispatch 真正生效（agent 决定要走就真的走，言行一致），与 DRAMA_FREE_MOVE 无关。
  2) `DRAMA_FREE_MOVE`/`npc_free_move` 现在**只**门控「导演自动聚场」`_gather_scene`(f05)：关时不主动搬人，
     开时才允许导演把反应 NPC 聚到玩家面前。

本测试证明这两条。离线、不起世界：dispatcher 用 __new__ 造（request_move 分支不依赖实例状态），
monkeypatch 父类 dispatch / ipc_helper.send_move_agent 验证委托与门控。
"""

from __future__ import annotations

import asyncio
import os
import sys

from agent_world.drama_demo.core.runner.drama_dispatcher import DramaActionDispatcher
from agent_world.drama_demo.shared.story_pack.scenario_adapter import is_free_move_enabled
from agent_world.world.dispatcher import ActionDispatcher


def test_flag_default_off() -> None:
    """DRAMA_FREE_MOVE 默认关；该开关现仅供 f05 _gather_scene 读（导演自动聚场门控）。"""
    os.environ.pop("DRAMA_FREE_MOVE", None)
    assert is_free_move_enabled() is False
    os.environ["DRAMA_FREE_MOVE"] = "1"
    try:
        assert is_free_move_enabled() is True
    finally:
        os.environ.pop("DRAMA_FREE_MOVE", None)


def _run_dispatch_records_delegation() -> dict:
    """造 dispatcher，monkeypatch 父类 dispatch，跑一次 request_move，返回记录。"""
    d = DramaActionDispatcher.__new__(DramaActionDispatcher)  # 不走 __init__
    rec: dict = {}

    async def fake_super(self, agent_id, action_type, t, **kw):  # noqa: ANN001
        rec["hit"] = (agent_id, str(action_type))
        return {"success": True, "delegated": True}

    orig = ActionDispatcher.dispatch
    ActionDispatcher.dispatch = fake_super
    try:
        rec["result"] = asyncio.run(
            d.dispatch(2, "request_move", 0, place_id="negotiation_room")
        )
    finally:
        ActionDispatcher.dispatch = orig
    return rec


def test_move_delegates_when_flag_off() -> None:
    """关旋钮时 request_move **不再被抑制**，照样委托父类真正生效（自主移动始终放行）。"""
    os.environ.pop("DRAMA_FREE_MOVE", None)
    rec = _run_dispatch_records_delegation()
    assert rec["result"].get("delegated") is True, rec
    assert rec["result"].get("noop") is not True, "request_move 不应再被吞成 noop"
    assert rec.get("hit") is not None, "关旋钮时 request_move 也应委托父类 dispatch"


def test_move_delegates_when_flag_on() -> None:
    """开旋钮时 request_move 同样委托父类（两种旋钮态行为一致——移动不再受此开关影响）。"""
    os.environ["DRAMA_FREE_MOVE"] = "1"
    try:
        rec = _run_dispatch_records_delegation()
    finally:
        os.environ.pop("DRAMA_FREE_MOVE", None)
    assert rec["result"].get("delegated") is True, rec
    assert rec.get("hit") is not None, "开旋钮时 request_move 也应委托父类 dispatch"


def test_gather_scene_gated_by_flag() -> None:
    """导演自动聚场 `_gather_scene` 才是受 DRAMA_FREE_MOVE 门控的那条路：关时不搬人、开时才搬。"""
    from agent_world.drama_demo.features.f05_story_routing import interpreter_routing
    from agent_world.drama_demo.http import ipc_helper

    moves: list = []

    def fake_send_move(client, *, agent_id, place_id, timeout):  # noqa: ANN001
        moves.append((int(agent_id), str(place_id)))

    orig = ipc_helper.send_move_agent
    ipc_helper.send_move_agent = fake_send_move
    try:
        # 关：_gather_scene 应为空操作（导演不主动搬人）
        os.environ.pop("DRAMA_FREE_MOVE", None)
        interpreter_routing._gather_scene(object(), "negotiation_room", [2], 1.0)
        assert moves == [], f"关旋钮时导演不应搬人，却搬了：{moves}"
        # 开：_gather_scene 应真的发移动指令
        os.environ["DRAMA_FREE_MOVE"] = "1"
        interpreter_routing._gather_scene(object(), "negotiation_room", [2], 1.0)
        assert moves == [(2, "negotiation_room")], f"开旋钮时导演应搬人，实际：{moves}"
        # 任何旋钮态都绝不搬玩家(agent 0)
        moves.clear()
        interpreter_routing._gather_scene(object(), "negotiation_room", [0], 1.0)
        assert moves == [], f"导演绝不搬玩家(agent 0)，却搬了：{moves}"
    finally:
        ipc_helper.send_move_agent = orig
        os.environ.pop("DRAMA_FREE_MOVE", None)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
    print(f"\nNPC 移动语义门控：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
