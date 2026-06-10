"""W4 回归：同地点私信必达（「NPC 不回玩家私信」bug 的根因防护）。

根因（已修复）：self-edge latency=0 时同场 RDC arrive_at=t，与引擎
「每拍推进 active agent 感知游标到 t」+「地点内随机决策顺序」叠加，
NPC 先于玩家决策的拍次该消息永远掉出 (last_seen, t] 感知窗口。
修复：self-edge latency=1 → 同场私信下一拍必达。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cyber_town.backend.config import DEFAULT_SCENARIO_PATH, LLMConfig
from cyber_town.backend.llm_client import make_llm_client
from cyber_town.backend.world_factory import build_world
from cyber_town.world_seed.loader import load_scenario

_MOCK_CFG = LLMConfig(base_url="http://mock", model="mock", api_key="mock")


@pytest.mark.asyncio
async def test_same_place_dm_arrives_next_tick(tmp_path: Path) -> None:
    """玩家私信同场 NPC：arrive_at 必须 = attempted_at + 1（不再同拍）。"""
    scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    client = make_llm_client(_MOCK_CFG, mock=True)
    asm = await build_world(scenario, tmp_path, client, _MOCK_CFG)

    # 玩家(0)与大山(3)同在 farm —— 按 E 同场私信场景
    asm.player.push_command(
        {"action": "send_message", "kwargs": {"target": 3, "content": "同场私信测试"}})
    await asm.world_step.run_one_tick()   # t=0 发出

    row = asm.world_db._conn.execute(  # noqa: SLF001
        "SELECT attempted_at, arrive_at, delivered FROM direct_message "
        "WHERE channel_type='RDC' AND content='同场私信测试'",
    ).fetchone()
    assert row is not None, "同场私信应成功投递（phi_rdc can_reach 不受影响）"
    attempted, arrive, delivered = row
    assert delivered == 1
    assert arrive == attempted + 1, (
        f"同场私信必须 1 拍延迟（arrive={arrive}, attempted={attempted}）——"
        "latency=0 会与引擎感知游标竞态导致约半数丢失"
    )

    # 关键不变量：引擎在发出拍已把 NPC 的 last_seen 推进到 t=0，
    # 下一拍 (last_seen=0, t=1] 窗口必须能命中这条消息
    hits = asm.world_db.fetch_arrived_for(3, t=1, last_seen=0)
    assert any(m.content == "同场私信测试" for m in hits), \
        "下一拍感知窗口必须包含同场私信（修复前此处约半数为空）"
