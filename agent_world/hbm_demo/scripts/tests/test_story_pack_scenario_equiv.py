#!/usr/bin/env python3
"""StoryPack→scenario 播种等价（G0-Slice6，dev_logs/45 §6 / dev_logs/46 C-1）。

证明：story_pack_to_scenario(HBM 参考包) 与 load_scenario(hbm_scenario.yaml) 在 seed_world /
build_kernel 消费的**全部键**上完全一致——即开关开启时，世界从 Story Pack 播种 == 从旧 scenario
播种，零行为差异。纯数据层，不起 Runner/Flask/LLM。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

from agent_world.hbm_demo.features.f01_session.constants import DEFAULT_CONFIG
from agent_world.hbm_demo.shared.config_loader import load_scenario
from agent_world.hbm_demo.shared.story_pack import load_story_pack
from agent_world.hbm_demo.shared.story_pack.scenario_adapter import story_pack_to_scenario

STORY_ID = "hbm_memory_war"


def _scn() -> Dict[str, Any]:
    return load_scenario(DEFAULT_CONFIG)


def _pack_scn() -> Dict[str, Any]:
    return story_pack_to_scenario(load_story_pack(STORY_ID))


def _norm_list(seq: List[Dict[str, Any]], *keys: str):
    return sorted(tuple(d.get(k) for k in keys) for d in seq)


def test_scalar_blocks_equal() -> None:
    a, b = _scn(), _pack_scn()
    assert a.get("simulation_id") == b.get("simulation_id")
    assert (a.get("runner") or {}) == (b.get("runner") or {}), (a.get("runner"), b.get("runner"))
    assert (a.get("clock") or {}) == (b.get("clock") or {}), (a.get("clock"), b.get("clock"))
    assert (a.get("llm") or {}) == (b.get("llm") or {}), (a.get("llm"), b.get("llm"))


def test_places_equal() -> None:
    a, b = _scn(), _pack_scn()
    # 逐 place 比较 place_id/capacity/attrs（attrs 是 seed 进 world.db 的，须字节一致）
    am = {p["place_id"]: p for p in a["places"]}
    bm = {p["place_id"]: p for p in b["places"]}
    assert set(am) == set(bm), (set(am), set(bm))
    for pid in am:
        assert am[pid].get("capacity") == bm[pid].get("capacity"), pid
        assert (am[pid].get("attrs") or {}) == (bm[pid].get("attrs") or {}), f"{pid} attrs 漂移"


def test_coverage_equal() -> None:
    a, b = _scn(), _pack_scn()
    assert _norm_list(a["coverage"], "src", "dst", "latency_ticks") == _norm_list(
        b["coverage"], "src", "dst", "latency_ticks"
    )


def test_capabilities_equal() -> None:
    a, b = _scn(), _pack_scn()
    assert _norm_list(a["capabilities"], "agent_id", "capability") == _norm_list(
        b["capabilities"], "agent_id", "capability"
    )


def test_relations_equal() -> None:
    a, b = _scn(), _pack_scn()
    assert _norm_list(a["relations"], "src", "dst", "type", "symmetric") == _norm_list(
        b["relations"], "src", "dst", "type", "symmetric"
    )


def test_groups_equal() -> None:
    a, b = _scn(), _pack_scn()
    am = {int(g["group_id"]): g for g in a["groups"]}
    bm = {int(g["group_id"]): g for g in b["groups"]}
    assert set(am) == set(bm)
    for gid in am:
        assert am[gid].get("name") == bm[gid].get("name"), gid
        assert sorted(am[gid].get("members") or []) == sorted(bm[gid].get("members") or []), gid
        assert int(am[gid].get("creator_id")) == int(bm[gid].get("creator_id")), gid


def test_agents_equal() -> None:
    a, b = _scn(), _pack_scn()
    am = {int(x["agent_id"]): x for x in a["agents"]}
    bm = {int(x["agent_id"]): x for x in b["agents"]}
    assert set(am) == set(bm), (set(am), set(bm))
    for aid in am:
        for key in ("name", "location", "soul", "long_term_goal", "current_state"):
            av = (am[aid].get(key) or "").strip() if isinstance(am[aid].get(key), str) else am[aid].get(key)
            bv = (bm[aid].get(key) or "").strip() if isinstance(bm[aid].get(key), str) else bm[aid].get(key)
            assert av == bv, f"agent {aid} 的 {key} 漂移:\n  scn ={av!r}\n  pack={bv!r}"


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
    print(f"\nStoryPack→scenario 播种等价：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
