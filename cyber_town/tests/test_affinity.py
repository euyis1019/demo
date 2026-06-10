"""M4 好感度测试：store clamp/幂等、主路拦截、规则法底噪、快照导出。"""

from __future__ import annotations

from pathlib import Path

import pytest

from cyber_town.backend.affinity import AffinityManager, AffinityStore
from cyber_town.backend.affinity.manager import DEFAULT_SEED, ADJUST_AFFINITY_TOOL
from cyber_town.backend.config import DEFAULT_SCENARIO_PATH, LLMConfig
from cyber_town.backend.llm_client import make_llm_client
from cyber_town.backend.snapshot import SnapshotBuilder
from cyber_town.backend.world_factory import build_world
from cyber_town.world_seed.loader import load_scenario

_MOCK_CFG = LLMConfig(base_url="http://mock", model="mock", api_key="mock")
_NAMES = {0: "农场主", 1: "老钱", 2: "阿香", 3: "大山"}


def _store(tmp_path: Path) -> AffinityStore:
    return AffinityStore(tmp_path / "affinity.db", player_id=0)


# ---------------- store ----------------

def test_store_clamp_and_default(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert s.get_score(1, 0) == 10            # 缺省底色
    assert s.apply_delta(1, 0, +200, t=1) == 100   # 上限 clamp
    assert s.apply_delta(1, 0, -500, t=2) == 0     # 下限 clamp


def test_store_rejects_player_as_holder(tmp_path: Path) -> None:
    s = _store(tmp_path)
    with pytest.raises(ValueError):
        s.apply_delta(0, 1, 5, t=1)           # 玩家不持有好感度
    with pytest.raises(ValueError):
        s.apply_delta(1, 1, 5, t=1)           # 不能对自己


def test_seed_idempotent(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.seed(DEFAULT_SEED)
    assert s.get_score(3, 0) == 30            # 大山→玩家 熟悉底色
    s.apply_delta(3, 0, +10, t=5)
    s.seed(DEFAULT_SEED)                      # 再灌不覆盖已有
    assert s.get_score(3, 0) == 40


# ---------------- manager 主路（私有工具拦截） ----------------

def test_llm_delta_clamped_via_private_tool(tmp_path: Path) -> None:
    s = _store(tmp_path)
    mgr = AffinityManager(s, _NAMES, player_id=0)

    class _FakeNpc:
        agent_id = 1
        name = "老钱"

    mgr._on_private_tool(_FakeNpc(), "adjust_affinity",
                         {"target": 0, "delta": 99, "reason": "test"}, t=3)
    assert s.get_score(1, 0) == 15            # 10 + clamp(99→+5)
    mgr._on_private_tool(_FakeNpc(), "adjust_affinity",
                         {"target": 0, "delta": -99}, t=4)
    assert s.get_score(1, 0) == 12            # 15 + clamp(-99→-3)


def test_level_mapping() -> None:
    assert AffinityManager.level_of(5)[0] == "陌生"
    assert AffinityManager.level_of(20)[0] == "熟悉"
    assert AffinityManager.level_of(45)[0] == "友好"
    assert AffinityManager.level_of(60)[0] == "亲密"
    assert AffinityManager.level_of(95)[0] == "挚友"


# ---------------- 集成：规则法底噪 + NPC 挂点 + 快照 ----------------

async def _build_with_affinity(tmp_path: Path):
    scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    client = make_llm_client(_MOCK_CFG, mock=True)
    asm = await build_world(scenario, tmp_path, client, _MOCK_CFG)
    store = AffinityStore(tmp_path / "affinity.db", player_id=0)
    store.seed(DEFAULT_SEED)
    mgr = AffinityManager(store, asm.name_directory, player_id=0)
    mgr.wire_npcs(asm.npcs)
    return asm, mgr, store


@pytest.mark.asyncio
async def test_wire_npcs_attaches_hooks(tmp_path: Path) -> None:
    asm, mgr, _ = await _build_with_affinity(tmp_path)
    for npc in asm.npcs:
        assert "adjust_affinity" in npc.private_tool_names
        assert npc.private_tool_handler is not None
        assert npc.prompt_suffix_provider is not None
        assert any(t["function"]["name"] == "adjust_affinity"
                   for t in npc.extra_tools)
    assert ADJUST_AFFINITY_TOOL in asm.npcs[0].extra_tools


@pytest.mark.asyncio
async def test_snapshot_carries_affinity(tmp_path: Path) -> None:
    asm, mgr, _ = await _build_with_affinity(tmp_path)
    builder = SnapshotBuilder(asm, tick_seconds=2.5, affinity_manager=mgr)
    report = await asm.world_step.run_one_tick()
    snap = await builder.build(report)
    data = snap["data"]
    assert "affinity" in data and data["affinity"], "快照应含全量好感度"
    assert data["agents"]["3"].get("affinity_to_player") is not None
    assert "affinity_to_player" not in data["agents"]["0"], "玩家自身无该字段"


@pytest.mark.asyncio
async def test_full_llm_parse_chain_intercepts_private_tool(tmp_path: Path) -> None:
    """完整链路（审查 AFF-002）：LLM 响应 → npc._extract_tool_calls 拦截
    adjust_affinity（不进引擎）→ 好感落库；speak_to_local 同拍照常返回引擎。
    """
    import json as _json
    from dataclasses import dataclass, field as dfield
    from typing import List as _List

    asm, mgr, store = await _build_with_affinity(tmp_path)
    dashan = next(n for n in asm.npcs if n.agent_id == 3)

    # 构造「同拍混合私有+引擎工具」的 OpenAI 同形响应
    @dataclass
    class _Fn:
        name: str
        arguments: str

    @dataclass
    class _Tc:
        function: _Fn

    @dataclass
    class _Msg:
        content: str = ""
        tool_calls: _List = dfield(default_factory=list)

    @dataclass
    class _Choice:
        message: _Msg

    @dataclass
    class _Resp:
        choices: _List

    resp = _Resp(choices=[_Choice(_Msg(tool_calls=[
        _Tc(_Fn("adjust_affinity",
                _json.dumps({"target": 0, "delta": 3, "reason": "新邻居送菜"}))),
        _Tc(_Fn("speak_to_local", _json.dumps({"content": "嗐，自己人客气啥。"}))),
    ]))])

    before = store.get_score(3, 0)
    agent_resp = dashan._extract_tool_calls(resp, t=2)  # noqa: SLF001 — 链路测试
    engine_calls = agent_resp.info["tool_calls"]

    # 私有工具被抽走：引擎只见 speak_to_local
    assert [c.tool_name for c in engine_calls] == ["speak_to_local"]
    # 好感已落库（+3）
    assert store.get_score(3, 0) == before + 3


@pytest.mark.asyncio
async def test_prompt_suffix_renders_present_only(tmp_path: Path) -> None:
    """第 6 段只渲染在场者（控 token），且含等级指引。"""
    asm, mgr, _ = await _build_with_affinity(tmp_path)
    dashan = next(n for n in asm.npcs if n.agent_id == 3)

    class _Obs:
        co_located_agents = [0]               # 大山与玩家同场

    text = dashan.prompt_suffix_provider(dashan, _Obs())
    assert "我对在场各人的态度" in text
    assert "adjust_affinity" in text, "W3：第6段应含主动评估引导"
    assert "农场主" in text and "熟悉" in text  # 种子 30 分=熟悉

    class _Empty:
        co_located_agents = []

    assert dashan.prompt_suffix_provider(dashan, _Empty()) == ""
