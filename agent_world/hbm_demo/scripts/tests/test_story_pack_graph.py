#!/usr/bin/env python3
"""Story Pack 数据层专项单测（G0-Slice1，dev_logs/45 §4）。

覆盖：
  1. HBM 参考包 story_graph.yaml 过 validate（0 违例）。
  2. 结构正确（4 节点 / 4 结局 / 7 边）。
  3. enumerate_all_paths 命中全部 4 个结局；get_reachable_endings 等于这 4 个。
  4. validate 闸门能拒绝坏图：环(V4) / 不可达结局(V6) / 悬空边(V3) / 结局作起点(V3)。
  5. meta.yaml 可加载（simulation_id 正确）。

可独立运行：``python3 scripts/tests/test_story_pack_graph.py``，也可被 pytest 发现。
纯数据层测试，不起 Runner/Flask、不连 LLM、不碰 sim/。
"""

from __future__ import annotations

import sys

from agent_world.hbm_demo.shared.story_pack import (
    StoryGraph,
    StoryPackValidationError,
    load_and_validate_story_graph,
    load_and_validate_story_pack,
    load_meta,
    load_story_graph,
    load_story_pack,
)

STORY_ID = "hbm_memory_war"

EXPECTED_NODES = {"phase1_reception", "phase2_private", "phase3_negotiation", "phase4_finale"}
EXPECTED_ENDINGS = {
    "ending_join_nvidia",
    "ending_seed_round",
    "ending_cold_deal",
    "ending_bad_reject",
}
EXPECTED_EDGES = {
    "node_a",
    "node_b",
    "node_c",
    "node_d_join",
    "node_d_seed",
    "node_d_cold",
    "bad_end_reject",
}


def test_hbm_pack_validates() -> None:
    graph = load_story_graph(STORY_ID)
    issues = graph.validate()
    assert issues == [], f"HBM 参考包不该有违例，却得到：{issues}"


def test_hbm_pack_structure() -> None:
    graph = load_story_graph(STORY_ID)
    assert set(graph.nodes) == EXPECTED_NODES, set(graph.nodes)
    assert set(graph.endings) == EXPECTED_ENDINGS, set(graph.endings)
    assert {e.id for e in graph.edges} == EXPECTED_EDGES, {e.id for e in graph.edges}
    assert graph.initial_node == "phase1_reception"
    # inject_agents 忠实映射 routing.PHASE_INJECT_AGENTS
    assert graph.nodes["phase1_reception"].inject_agents == [1]
    assert graph.nodes["phase3_negotiation"].inject_agents == [2, 3, 4, 5, 6]


def test_all_endings_reachable() -> None:
    graph = load_story_graph(STORY_ID)
    assert set(graph.get_reachable_endings()) == EXPECTED_ENDINGS
    # 枚举路径，收集每条路径的终点（结局）
    paths = graph.enumerate_all_paths()
    reached = {p[-1] for p in paths if p and p[-1] in graph.endings}
    assert reached == EXPECTED_ENDINGS, f"枚举路径只到达了 {reached}"
    # 节点子图无环 → 拓扑排序成功且覆盖全部节点
    assert set(graph.topological_sort()) == EXPECTED_NODES


def test_load_and_validate_helper() -> None:
    graph = load_and_validate_story_graph(STORY_ID)  # 不抛即通过
    assert isinstance(graph, StoryGraph)


def test_meta_loads() -> None:
    meta = load_meta(STORY_ID)
    assert meta["simulation_id"] == STORY_ID
    assert meta["player"]["agent_id"] == 0


# ---------- validate 闸门：拒绝坏图 ----------

def _graph(nodes, endings, edges, initial) -> StoryGraph:
    return StoryGraph.from_mapping(
        {"initial_node": initial, "nodes": nodes, "endings": endings, "edges": edges}
    )


def test_reject_cycle() -> None:
    g = _graph(
        nodes=[{"id": "a"}, {"id": "b"}],
        endings=[{"id": "win"}],
        edges=[
            {"id": "e1", "from": "a", "to": "b"},
            {"id": "e2", "from": "b", "to": "a"},  # 环
            {"id": "e3", "from": "a", "to": "win"},
        ],
        initial="a",
    )
    issues = g.validate()
    assert any(it.startswith("[V4]") for it in issues), issues


def test_reject_unreachable_ending() -> None:
    g = _graph(
        nodes=[{"id": "a"}],
        endings=[{"id": "win"}, {"id": "lost"}],  # lost 无入边
        edges=[{"id": "e1", "from": "a", "to": "win"}],
        initial="a",
    )
    issues = g.validate()
    assert any(it.startswith("[V6]") for it in issues), issues


def test_reject_dangling_edge() -> None:
    g = _graph(
        nodes=[{"id": "a"}],
        endings=[{"id": "win"}],
        edges=[{"id": "e1", "from": "a", "to": "ghost"}],  # ghost 不存在
        initial="a",
    )
    issues = g.validate()
    assert any(it.startswith("[V3]") for it in issues), issues


def test_reject_ending_as_source() -> None:
    g = _graph(
        nodes=[{"id": "a"}],
        endings=[{"id": "win"}],
        edges=[
            {"id": "e1", "from": "a", "to": "win"},
            {"id": "e2", "from": "win", "to": "a"},  # 结局当起点，破坏终结性
        ],
        initial="a",
    )
    issues = g.validate()
    assert any(it.startswith("[V3]") for it in issues), issues


def test_validate_or_raise_raises() -> None:
    g = _graph(
        nodes=[{"id": "a"}],
        endings=[{"id": "win"}, {"id": "lost"}],
        edges=[{"id": "e1", "from": "a", "to": "win"}],
        initial="a",
    )
    try:
        g.validate_or_raise()
    except StoryPackValidationError as exc:
        assert exc.issues
    else:
        raise AssertionError("坏图应抛 StoryPackValidationError")


# ---------- Slice2：整包聚合 + 跨文件引用闭合 ----------

def test_hbm_full_pack_validates() -> None:
    pack = load_story_pack(STORY_ID)
    issues = pack.validate()
    assert issues == [], f"HBM 整包不该有违例，却得到：{issues}"
    # 聚合加载到位
    assert pack.agent_ids() == {0, 1, 2, 3, 4, 5, 6, 7}, pack.agent_ids()
    assert pack.place_ids() == {
        "nvidia_reception",
        "negotiation_room",
        "jensen_private_room",
        "openai_hq",
    }, pack.place_ids()
    assert pack.relation_type_names() == {
        "subordinate",
        "colleague",
        "business_partner",
        "ally",
    }
    assert "approve_keywords" in pack.keyword_set_names()
    assert "approve_visitor" in pack.story_advance_signals()
    assert "max_turns_phase1_without_approve" in pack.param_names()


def test_load_and_validate_pack_helper() -> None:
    load_and_validate_story_pack(STORY_ID)  # 不抛即通过


def test_pack_rejects_unknown_inject_agent() -> None:
    pack = load_story_pack(STORY_ID)
    pack.graph.nodes["phase1_reception"].inject_agents.append(99)  # 不存在的 agent
    issues = pack.validate()
    assert any(it.startswith("[X1]") for it in issues), issues


def test_pack_rejects_unknown_move_place() -> None:
    pack = load_story_pack(STORY_ID)
    edge = next(e for e in pack.graph.edges if e.id == "node_a")
    edge.actions.append({"type": "move_agent", "agent": 2, "to": "ghost_room"})
    issues = pack.validate()
    assert any(it.startswith("[X2]") for it in issues), issues


def test_pack_rejects_unknown_keyword_set() -> None:
    pack = load_story_pack(STORY_ID)
    # 删掉 approve_keywords，让 node_a trigger 的引用悬空
    del pack.signals["keyword_sets"]["approve_keywords"]
    issues = pack.validate()
    assert any(it.startswith("[X4]") for it in issues), issues


def test_pack_rejects_unknown_relation_type() -> None:
    pack = load_story_pack(STORY_ID)
    pack.relations["relations"].append({"src": 1, "dst": 7, "type": "nemesis"})
    issues = pack.validate()
    assert any(it.startswith("[X5]") for it in issues), issues


def test_pack_faithful_to_scenario() -> None:
    """G0 回归锚点：HBM 参考包的世界原语必须与 hbm_scenario.yaml 逐项一致(无漂移)。"""
    import yaml

    from agent_world.hbm_demo.shared.prompt_paths import scenario_path

    scn = yaml.safe_load(scenario_path().read_text(encoding="utf-8"))
    pack = load_story_pack(STORY_ID)

    def sset(seq, *keys):
        return sorted(tuple(d.get(k) for k in keys) for d in seq)

    assert sset(scn["places"], "place_id", "capacity") == sset(
        pack.places["places"], "place_id", "capacity"
    )
    assert sset(scn["coverage"], "src", "dst", "latency_ticks") == sset(
        pack.places["coverage"], "src", "dst", "latency_ticks"
    )
    assert sset(scn["agents"], "agent_id", "name", "location") == sset(
        pack.agents["agents"], "agent_id", "name", "location"
    )
    assert sset(scn["relations"], "src", "dst", "type") == sset(
        pack.relations["relations"], "src", "dst", "type"
    )
    assert sset(scn["groups"], "group_id", "name", "creator_id") == sset(
        pack.groups["groups"], "group_id", "name", "creator_id"
    )
    # CapabilityTable 播种一致：scenario.capabilities 行 == 各 agent.capabilities 展开
    scn_caps = sorted((c["agent_id"], c["capability"]) for c in scn["capabilities"])
    pack_caps = sorted(
        (a["agent_id"], cap)
        for a in pack.agents["agents"]
        for cap in (a.get("capabilities") or [])
    )
    assert scn_caps == pack_caps, f"能力播种漂移：{scn_caps} vs {pack_caps}"
    # soul 全文一致
    scn_soul = {a["agent_id"]: (a.get("soul") or "").strip() for a in scn["agents"]}
    pack_soul = {a["agent_id"]: (a.get("soul") or "").strip() for a in pack.agents["agents"]}
    assert scn_soul == pack_soul, "agent soul 文本漂移"


def test_pack_optional_files_degrade() -> None:
    # 去掉 agents/places（模拟可选文件缺失）→ 不应因引用闭合报错（降级跳过）
    pack = load_story_pack(STORY_ID)
    pack.agents = {}
    pack.places = {}
    issues = [it for it in pack.validate() if it.startswith(("[X1]", "[X2]"))]
    assert issues == [], f"缺 agents/places 时应降级跳过 X1/X2，却报：{issues}"


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
    total = len(tests)
    print(f"\nstory_pack 单测：{total - failed}/{total} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
