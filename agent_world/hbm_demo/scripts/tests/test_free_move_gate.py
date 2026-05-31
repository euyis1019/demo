#!/usr/bin/env python3
"""自由移动旋钮门控（旋钮2，dev_logs/46 B-3）。

证明：HBM_FREE_MOVE 默认关时 HbmActionDispatcher 仍抑制 agent 的 request_move（旧脚本搬人，
行为不变）；开关开启时 request_move 落到通用 dispatcher（super().dispatch）真正生效。
离线、不起世界——用 __new__ 造 dispatcher（request_move 分支不依赖实例状态），monkeypatch
父类 dispatch 验证委托。
"""

from __future__ import annotations

import asyncio
import os
import sys

from agent_world.hbm_demo.core.runner.hbm_dispatcher import HbmActionDispatcher
from agent_world.hbm_demo.shared.story_pack.scenario_adapter import is_free_move_enabled
from agent_world.world.dispatcher import ActionDispatcher


def test_flag_default_off() -> None:
    os.environ.pop("HBM_FREE_MOVE", None)
    assert is_free_move_enabled() is False
    os.environ["HBM_FREE_MOVE"] = "1"
    try:
        assert is_free_move_enabled() is True
    finally:
        os.environ.pop("HBM_FREE_MOVE", None)


def test_move_suppressed_when_off() -> None:
    os.environ.pop("HBM_FREE_MOVE", None)
    d = HbmActionDispatcher.__new__(HbmActionDispatcher)  # 不走 __init__
    r = asyncio.run(d.dispatch(2, "request_move", 0, place_id="negotiation_room"))
    assert r.get("noop") is True and r.get("reason") == "hbm_move_ipc_only", r


def test_move_delegates_when_on() -> None:
    d = HbmActionDispatcher.__new__(HbmActionDispatcher)
    rec = {}

    async def fake_super(self, agent_id, action_type, t, **kw):  # noqa: ANN001
        rec["hit"] = (agent_id, str(action_type))
        return {"success": True, "delegated": True}

    orig = ActionDispatcher.dispatch
    ActionDispatcher.dispatch = fake_super
    os.environ["HBM_FREE_MOVE"] = "1"
    try:
        r = asyncio.run(d.dispatch(2, "request_move", 0, place_id="negotiation_room"))
        assert r.get("delegated") is True, r
        assert rec.get("hit") is not None, "开关开启时应委托父类 dispatch"
    finally:
        ActionDispatcher.dispatch = orig
        os.environ.pop("HBM_FREE_MOVE", None)


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
    print(f"\n自由移动门控：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
