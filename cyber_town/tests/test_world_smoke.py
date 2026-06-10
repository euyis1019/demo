"""全链路冒烟：Mock LLM 装配真实引擎跑若干拍，验收核心不变量。

覆盖（M0 验收的自动化版）：
* V4：同地点 F2F 送达（依赖 loader 的 self-edge 补全）；
* RDC 跨地点 arrive_at = attempted_at + 1；
* 玩家命令经队列注入后真实落库；
* dispatcher / perception 非 None 断言（C1 对策）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cyber_town.backend.config import DEFAULT_SCENARIO_PATH, LLMConfig
from cyber_town.backend.llm_client import make_llm_client
from cyber_town.backend.world_factory import build_world
from cyber_town.world_seed.loader import load_scenario

_MOCK_CFG = LLMConfig(base_url="http://mock", model="mock", api_key="mock")


async def _build(tmp_path: Path):
    scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    client = make_llm_client(_MOCK_CFG, mock=True)
    return await build_world(
        scenario, tmp_path, client, _MOCK_CFG,
    )


@pytest.mark.asyncio
async def test_world_runs_and_f2f_delivered(tmp_path: Path) -> None:
    asm = await _build(tmp_path)
    assert asm.dispatcher is not None and asm.perception is not None

    for _ in range(4):
        report = await asm.world_step.run_one_tick()
        assert "failures" in report

    conn = asm.world_db._conn  # noqa: SLF001 — 测试直读
    f2f = conn.execute(
        "SELECT COUNT(*) FROM direct_message WHERE channel_type='F2F' AND delivered=1"
    ).fetchone()[0]
    assert f2f > 0, "V4 失败：同地点 F2F 未送达（self-edge 补全失效？）"


@pytest.mark.asyncio
async def test_rdc_one_tick_delay(tmp_path: Path) -> None:
    asm = await _build(tmp_path)
    for _ in range(4):
        await asm.world_step.run_one_tick()
    rows = asm.world_db._conn.execute(  # noqa: SLF001
        "SELECT attempted_at, arrive_at FROM direct_message WHERE channel_type='RDC'"
    ).fetchall()
    assert rows, "Mock 剧本应产生 RDC 消息"
    for attempted, arrive in rows:
        assert arrive == attempted + 1, "跨地点 RDC 应恰好 1 拍延迟"


@pytest.mark.asyncio
async def test_player_command_lands_in_world(tmp_path: Path) -> None:
    asm = await _build(tmp_path)
    asm.player.push_command(
        {"action": "speak_to_local", "kwargs": {"content": "测试：玩家说话"}}
    )
    await asm.world_step.run_one_tick()
    row = asm.world_db._conn.execute(  # noqa: SLF001
        "SELECT COUNT(*) FROM direct_message "
        "WHERE sender_id=? AND content LIKE '测试：玩家说话%'",
        (asm.player.agent_id,),
    ).fetchone()[0]
    assert row > 0, "玩家命令未经总线落库"
