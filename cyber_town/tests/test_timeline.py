"""M6 档案时间线测试：归并/折叠/类型/REST 端点。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cyber_town.backend.config import DEFAULT_SCENARIO_PATH, LLMConfig
from cyber_town.backend.llm_client import make_llm_client
from cyber_town.backend.main import create_app
from cyber_town.backend.timeline import build_timeline
from cyber_town.backend.world_factory import build_world
from cyber_town.world_seed.loader import load_scenario

_MOCK_CFG = LLMConfig(base_url="http://mock", model="mock", api_key="mock")


async def _world(tmp_path: Path):
    scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    client = make_llm_client(_MOCK_CFG, mock=True)
    return await build_world(scenario, tmp_path, client, _MOCK_CFG)


@pytest.mark.asyncio
async def test_timeline_merges_actions_and_messages(tmp_path: Path) -> None:
    """大山（Mock 剧本）：说话/OS/私信/群发/移动 全类型入时间线且有序。"""
    asm = await _world(tmp_path)
    for _ in range(6):
        await asm.world_step.run_one_tick()

    entries = build_timeline(asm, 3, limit=60)
    types = {e["type"] for e in entries}
    # Mock 剧本 t0 说话 / t1 OS / t2 私信 / t3 群发 / t4 移动
    for expect in ("speak", "os", "dm_out", "grp_out", "move"):
        assert expect in types, f"缺类型 {expect}：{types}"
    # 时间升序 + HH:MM 格式
    ts = [e["t"] for e in entries]
    assert ts == sorted(ts)
    assert all(":" in e["time"] for e in entries)
    # F2F 扇出折叠：t=0 的发言只出现一次
    speaks_t0 = [e for e in entries if e["type"] == "speak" and e["t"] == 0]
    assert len(speaks_t0) == 1, "F2F 扇出应折叠为一句"
    # 移动条目用中文地名（种子 display_name），不露英文 place_id
    moves = [e for e in entries if e["type"] == "move"]
    assert moves and "广场" in moves[0]["text"], f"应显示中文地名：{moves}"


@pytest.mark.asyncio
async def test_timeline_includes_received_side(tmp_path: Path) -> None:
    """老钱收到大山的私信 → 老钱时间线含 dm_in（双向可见）。"""
    asm = await _world(tmp_path)
    for _ in range(5):
        await asm.world_step.run_one_tick()
    entries = build_timeline(asm, 1, limit=60)
    assert any(e["type"] == "dm_in" and "大山" in e["text"] for e in entries), \
        "老钱档案里应能看到收到大山的私信"


def test_timeline_rest_endpoint(tmp_path: Path) -> None:
    app = create_app(mock=True, tick_seconds=0.05,
                     sim_dir=str(tmp_path))
    with TestClient(app) as client:
        import time
        time.sleep(0.5)  # 让世界跑几拍
        r = client.get("/agents/3/timeline")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "大山" and isinstance(body["entries"], list)
        assert client.get("/agents/99/timeline").status_code == 404
