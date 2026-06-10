"""SnapshotBuilder 测试：游标去重（审计 B-3 对策）与分片字段完整性。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from cyber_town.backend.config import DEFAULT_SCENARIO_PATH, LLMConfig
from cyber_town.backend.llm.client import make_llm_client
from cyber_town.backend.api.snapshot import SnapshotBuilder
from cyber_town.backend.runtime.world_factory import build_world
from cyber_town.world_seed.loader import load_scenario

_MOCK_CFG = LLMConfig(base_url="http://mock", model="mock", api_key="mock")


async def _build(tmp_path: Path):
    scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    client = make_llm_client(_MOCK_CFG, mock=True)
    asm = await build_world(scenario, tmp_path, client, _MOCK_CFG)
    return asm, SnapshotBuilder(asm)


def _all_message_ids(snap: Dict[str, Any]) -> List[int]:
    """直达类消息 id（同一 message_id 在 recipient=玩家 的行只会有一条）。"""
    pv = snap["data"]["player_view"]
    ids: List[int] = []
    for key in ("incoming", "f2f", "group"):
        ids += [m["message_id"] for m in pv[key]]
    return ids


def _overheard_ids(snap: Dict[str, Any]) -> List[int]:
    """旁听消息单独去重（与直达类可合法共享 message_id，分开检查）。"""
    return [m["message_id"] for m in snap["data"]["player_view"]["overheard"]]


@pytest.mark.asyncio
async def test_snapshot_shape_and_no_duplicate_messages(tmp_path: Path) -> None:
    asm, builder = await _build(tmp_path)

    seen: set = set()
    seen_overheard: set = set()
    for _ in range(6):
        report = await asm.world_step.run_one_tick()
        snap = await builder.build(report)

        # 信封与分片字段齐全
        assert snap["type"] == "snapshot" and "t" in snap
        data = snap["data"]
        for key in ("world_time", "places", "agents", "player_view",
                    "contacts", "moves", "recent_arrivals", "recent_departures"):
            assert key in data, f"快照缺分片：{key}"

        # 游标去重：任何消息 id 不得跨帧重复出现（直达与旁听分开核——
        # 引擎 fetch_overhear_for 是闭区间 >=，曾导致旁听每帧重复，审查 B-1）
        ids = _all_message_ids(snap)
        dup = [i for i in ids if i in seen]
        assert not dup, f"快照直达消息重复推送：{dup}"
        seen.update(ids)

        o_ids = _overheard_ids(snap)
        o_dup = [i for i in o_ids if i in seen_overheard]
        assert not o_dup, f"快照旁听消息重复推送：{o_dup}"
        seen_overheard.update(o_ids)

    # Mock 剧本 t=0 大山对玩家 F2F、t=3 群发——玩家视角必有消息流入
    assert seen, "6 拍后玩家视角不应一无所获"


@pytest.mark.asyncio
async def test_snapshot_bubble_and_occupants(tmp_path: Path) -> None:
    asm, builder = await _build(tmp_path)
    report = await asm.world_step.run_one_tick()  # t=0：大山在 farm 说话
    snap = await builder.build(report)
    data = snap["data"]

    # 大山(3) 本拍说了话 → bubble 非空；玩家(0)/老钱(1) 没说 → None
    assert data["agents"]["3"]["bubble"], "说话者应有 bubble"
    assert data["agents"]["1"]["bubble"] is None

    # 占用者与 agents.location 一致
    for aid, info in data["agents"].items():
        assert int(aid) in data["places"][info["location"]]["occupants"]


@pytest.mark.asyncio
async def test_hello_frame(tmp_path: Path) -> None:
    asm, builder = await _build(tmp_path)
    hello = builder.hello()
    assert hello["type"] == "hello_ack"
    d = hello["data"]
    assert d["player_agent_id"] == asm.player.agent_id
    assert d["tick_interval_ms"] == 2500  # 协议契约：心跳间隔在 hello 给出
    assert {p["place_id"] for p in d["places"]} == {"farm", "square", "saloon"}
    assert d["groups"] and d["groups"][0]["group_id"] == 100
