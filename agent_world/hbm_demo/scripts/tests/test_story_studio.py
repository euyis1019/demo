#!/usr/bin/env python3
"""story_studio G1 单测（dev_logs/45 §6 G1 验收）。

覆盖：brief/designer schema 校验、安全红线(拒 sim/)、import 图红线(不引 kernel/seed/world_db/http)、
落盘+validate 骨架(由 DesignerOutput 落出 story_graph 骨架)、base_agent 生成→校验→重试。
纯离线：LLM 客户端用 fake，不连网络/key；写盘只用临时目录。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from agent_world.hbm_demo.tools.story_studio import (
    DESIGNER_OUTPUT_SCHEMA,
    StoryStudioError,
    StoryStudioSafetyError,
    assert_safe_target,
    call_json_with_schema,
    compile_pack,
    designer_output_to_story_graph,
    validate_against,
    validate_brief,
)

# 一个最小可用 brief
_GOOD_BRIEF = {
    "premise": "测试世界",
    "player": {"identity": "外来者", "role": "player", "is_outsider": True},
    "characters": [{"name": "甲", "faction": "f1"}],
}

# 一个最小可用 DesignerOutput（两节点一结局，DAG 合法）
_GOOD_DESIGNER = {
    "initial_node": "n1",
    "nodes": [{"id": "n1", "beats_label": "第一幕"}, {"id": "n2", "beats_label": "第二幕"}],
    "endings": [{"id": "win", "kind": "good"}],
    "edges": [
        {"id": "e1", "from": "n1", "to": "n2"},
        {"id": "e2", "from": "n2", "to": "win"},
    ],
}


def test_brief_schema_accepts_and_rejects() -> None:
    assert validate_brief(_GOOD_BRIEF) == []
    bad = {"premise": "缺 player"}
    issues = validate_brief(bad)
    assert any("player" in it for it in issues), issues
    bad2 = {"player": {"identity": "x"}}  # 缺 role
    assert validate_brief(bad2), "缺 role 应报错"


def test_designer_schema_accepts_and_rejects() -> None:
    assert validate_against(_GOOD_DESIGNER, DESIGNER_OUTPUT_SCHEMA) == []
    bad = {"initial_node": "n1", "nodes": [], "endings": [], "edges": []}
    assert validate_against(bad, DESIGNER_OUTPUT_SCHEMA), "空 nodes/edges 应报错"


def test_safety_rejects_sim_and_source() -> None:
    hbm_root = Path(__file__).resolve().parents[2]  # .../hbm_demo
    for forbidden in (hbm_root / "sim" / "x", hbm_root / "core" / "x", hbm_root / "features" / "x"):
        try:
            assert_safe_target(forbidden)
        except StoryStudioSafetyError:
            pass
        else:
            raise AssertionError(f"应拒绝写入红线目录：{forbidden}")
    # 临时目录(包外)应放行
    tmp = Path(tempfile.mkdtemp())
    try:
        assert assert_safe_target(tmp) == tmp.resolve()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_compile_writes_valid_skeleton() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        sections = {
            "meta": {"schema_version": 1, "simulation_id": "studio_selftest", "player": {"agent_id": 0}},
            "story_graph": designer_output_to_story_graph(_GOOD_DESIGNER),
        }
        result = compile_pack(sections, story_id="studio_selftest", target_dir=tmp)
        assert result.ok, f"骨架应过 validate，却报：{result.issues}"
        assert (tmp / "story_graph.yaml").is_file()
        assert (tmp / "meta.yaml").is_file()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_compile_rejects_bad_graph() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        # 不可达结局 → validate 应报 [V6]
        bad_designer = {
            "initial_node": "n1",
            "nodes": [{"id": "n1"}],
            "endings": [{"id": "win", "kind": "good"}, {"id": "lost", "kind": "bad"}],
            "edges": [{"id": "e1", "from": "n1", "to": "win"}],
        }
        sections = {"story_graph": designer_output_to_story_graph(bad_designer)}
        result = compile_pack(sections, story_id="studio_bad", target_dir=tmp)
        assert not result.ok and any(it.startswith("[V6]") for it in result.issues), result.issues
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_base_agent_generate_validate_retry() -> None:
    import json

    # fake client：第一次返回非法(空 nodes)，第二次返回合法 → 重试后成功
    calls = {"n": 0}

    def flaky_client(system: str, user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"initial_node": "n1", "nodes": [], "endings": [], "edges": []})
        return json.dumps(_GOOD_DESIGNER)

    out = call_json_with_schema(
        flaky_client, system="sys", user="生成故事图", schema=DESIGNER_OUTPUT_SCHEMA, label="designer"
    )
    assert out["initial_node"] == "n1" and calls["n"] == 2

    # 始终非法 → 重试耗尽抛错
    def bad_client(system: str, user: str) -> str:
        return "not json at all"

    try:
        call_json_with_schema(bad_client, system="s", user="u", schema=DESIGNER_OUTPUT_SCHEMA)
    except StoryStudioError:
        pass
    else:
        raise AssertionError("始终非法应抛 StoryStudioError")


def test_designer_agent_with_fake_client() -> None:
    import json

    from agent_world.hbm_demo.tools.story_studio import Designer

    def fake(system: str, user: str) -> str:
        return json.dumps(_GOOD_DESIGNER)

    out = Designer(fake).run(_GOOD_BRIEF)
    assert out["initial_node"] == "n1"
    assert {n["id"] for n in out["nodes"]} == {"n1", "n2"}


def test_generate_pipeline_happy_path() -> None:
    import json
    import tempfile

    from agent_world.hbm_demo.tools.story_studio import generate

    def fake(system: str, user: str) -> str:
        return json.dumps(_GOOD_DESIGNER)

    tmp = Path(tempfile.mkdtemp())
    try:
        result = generate(_GOOD_BRIEF, story_id="studio_gen", client=fake, target_dir=tmp)
        assert result.ok, result.issues
        assert (tmp / "story_graph.yaml").is_file() and (tmp / "meta.yaml").is_file()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_generate_regenerate_loop_converges() -> None:
    """Designer 第一版产环图(validate V4 失败)→回灌反馈→第二版合法 → 回路收敛。"""
    import json
    import tempfile

    from agent_world.hbm_demo.tools.story_studio import generate

    cyclic = {
        "initial_node": "n1",
        "nodes": [{"id": "n1"}, {"id": "n2"}],
        "endings": [{"id": "win", "kind": "good"}],
        "edges": [
            {"id": "e1", "from": "n1", "to": "n2"},
            {"id": "e2", "from": "n2", "to": "n1"},  # 环
            {"id": "e3", "from": "n1", "to": "win"},
        ],
    }
    calls = {"n": 0}

    def fake(system: str, user: str) -> str:
        calls["n"] += 1
        # 第一次产环图(过 schema 但 validate V4 失败)，之后产合法图
        return json.dumps(cyclic if calls["n"] == 1 else _GOOD_DESIGNER)

    tmp = Path(tempfile.mkdtemp())
    try:
        result = generate(_GOOD_BRIEF, story_id="studio_loop", client=fake, target_dir=tmp, max_rounds=3)
        assert result.ok, result.issues
        assert calls["n"] == 2, f"应在第 2 轮收敛，实际 {calls['n']} 轮"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_generate_raises_after_max_rounds() -> None:
    import json
    import tempfile

    from agent_world.hbm_demo.tools.story_studio import generate

    bad = {
        "initial_node": "n1",
        "nodes": [{"id": "n1"}],
        "endings": [{"id": "win", "kind": "good"}, {"id": "lost", "kind": "bad"}],
        "edges": [{"id": "e1", "from": "n1", "to": "win"}],  # lost 永不可达 → V6
    }

    def always_bad(system: str, user: str) -> str:
        return json.dumps(bad)

    tmp = Path(tempfile.mkdtemp())
    try:
        generate(_GOOD_BRIEF, story_id="studio_fail", client=always_bad, target_dir=tmp, max_rounds=2)
    except StoryStudioError:
        pass
    else:
        raise AssertionError("始终不可达结局应在轮次耗尽后抛 StoryStudioError")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- G3：完整流水线（Designer+Casting+Writer）----

_G3_DESIGNER = {
    "initial_node": "n1",
    "nodes": [{"id": "n1", "beats_label": "序", "summary": "开场"},
              {"id": "n2", "beats_label": "终", "summary": "结尾"}],
    "endings": [{"id": "win", "kind": "good", "summary": "赢"},
                {"id": "lose", "kind": "bad", "summary": "输"}],
    "edges": [{"id": "adv", "from": "n1", "to": "n2"},
              {"id": "fin", "from": "n2", "to": "win"},
              {"id": "fail", "from": "n1", "to": "lose"}],
}
_G3_CASTING = {
    "agents": [
        {"agent_id": 0, "name": "玩家", "location": "hall", "capabilities": [],
         "soul": "", "long_term_goal": "", "current_state": ""},
        {"agent_id": 1, "name": "守门人", "location": "hall", "capabilities": ["signal_uplink"],
         "soul": "严谨", "long_term_goal": "守门", "current_state": "值班"},
    ],
    "places": [{"place_id": "hall", "capacity": 5, "attrs": {"summary": "大厅"}}],
    "coverage": [{"src": "hall", "dst": "hall", "latency_ticks": 0}],
    "relations": [], "relation_types": [], "groups": [],
}
_G3_WRITER = {
    "nodes": [{"id": "n1", "inject_agents": [1], "place_focus": "hall", "window_since": "start_tick"},
              {"id": "n2", "inject_agents": [1], "place_focus": "hall", "window_since": "phase2_start_tick"}],
    "edges": [{"id": "adv", "legacy_label": "A", "trigger": {"type": "story_advance", "signal": "go_on"}, "actions": []},
              {"id": "fin", "trigger": {"type": "story_advance", "signal": "finish"}, "actions": []},
              {"id": "fail", "trigger": {"type": "story_advance", "signal": "reject"}, "actions": []}],
    "signals": {"story_advance": {"enabled": True, "valid_signals": ["go_on", "finish", "reject"]},
                "keyword_sets": {}, "params": {}},
}


def _routing_fake(designer=None, casting=None, writer=None):
    """按 system prompt 路由到对应 agent 的固定输出。"""
    import json

    d = designer if designer is not None else _G3_DESIGNER
    c = casting if casting is not None else _G3_CASTING
    w = writer if writer is not None else _G3_WRITER

    def fake(system: str, user: str) -> str:
        if "设计师" in system:
            return json.dumps(d)
        if "选角" in system:
            return json.dumps(c)
        if "编剧" in system:
            return json.dumps(w)
        raise AssertionError("未知 agent system prompt")

    return fake


def test_generate_full_produces_valid_complete_pack() -> None:
    import tempfile

    from agent_world.hbm_demo.shared.story_pack import load_story_pack
    from agent_world.hbm_demo.tools.story_studio import generate_full

    tmp = Path(tempfile.mkdtemp())
    try:
        result = generate_full(_GOOD_BRIEF, story_id="studio_full", client=_routing_fake(),
                               target_dir=tmp, max_rounds=2)
        assert result.ok, f"完整包应过 V+X 校验：{result.issues}"
        # 全部世界原语文件都落了盘
        for f in ("meta", "story_graph", "places", "agents", "relations", "relation_types", "groups", "signals"):
            assert (tmp / f"{f}.yaml").is_file(), f"缺 {f}.yaml"
        # 从该目录就地加载并复核 V+X 干净，且枚举路径命中两个结局
        from agent_world.hbm_demo.tools.story_studio.orchestrator import _load_pack_from_dir
        pack = _load_pack_from_dir("studio_full", tmp)
        assert pack.validate() == []
        reached = {p[-1] for p in pack.graph.enumerate_all_paths() if p[-1] in pack.graph.endings}
        assert reached == {"win", "lose"}, reached
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_generate_full_regenerates_on_xref_break() -> None:
    """Writer 第一版 inject 一个不存在的 agent(X1 失败)→回灌→第二版修好 → 回路收敛。"""
    import tempfile

    from agent_world.hbm_demo.tools.story_studio import generate_full

    broken_writer = {
        "nodes": [{"id": "n1", "inject_agents": [99], "place_focus": "hall", "window_since": "start_tick"},
                  {"id": "n2", "inject_agents": [1], "place_focus": "hall", "window_since": "phase2_start_tick"}],
        "edges": _G3_WRITER["edges"],
        "signals": _G3_WRITER["signals"],
    }
    calls = {"writer": 0}
    import json

    def fake(system: str, user: str) -> str:
        if "设计师" in system:
            return json.dumps(_G3_DESIGNER)
        if "选角" in system:
            return json.dumps(_G3_CASTING)
        if "编剧" in system:
            calls["writer"] += 1
            return json.dumps(broken_writer if calls["writer"] == 1 else _G3_WRITER)
        raise AssertionError("未知 agent")

    tmp = Path(tempfile.mkdtemp())
    try:
        result = generate_full(_GOOD_BRIEF, story_id="studio_xref", client=fake, target_dir=tmp, max_rounds=3)
        assert result.ok, result.issues
        assert calls["writer"] == 2, f"应在第 2 轮收敛，实际 {calls['writer']}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- G4：人在环 review + 局部重生成 ----

def test_review_renders_pack() -> None:
    from agent_world.hbm_demo.shared.story_pack import load_story_pack
    from agent_world.hbm_demo.tools.story_studio import render_review

    pack = load_story_pack("canglan_sword")
    text = render_review(pack)
    assert "Story Pack 审阅：canglan_sword" in text
    assert pack.graph.initial_node in text  # 初始节点渲染出
    assert any(eid in text for eid in pack.graph.endings)  # 至少一个结局渲染出
    assert "✓ 校验通过" in text  # canglan 包应渲染为校验通过


def test_regenerate_writer_keeps_cast_and_graph() -> None:
    """局部重生成 writer 层：先用完整流水线产一个包，再只重生 writer，cast/图不变且仍过校验。"""
    import json
    import tempfile

    from agent_world.hbm_demo.tools.story_studio import generate_full, regenerate_writer
    from agent_world.hbm_demo.tools.story_studio.orchestrator import _load_pack_from_dir

    tmp = Path(tempfile.mkdtemp())
    try:
        # 先产完整包
        gen_result = generate_full(_GOOD_BRIEF, story_id="studio_regen", client=_routing_fake(), target_dir=tmp)
        assert gen_result.ok, gen_result.issues
        before = _load_pack_from_dir("studio_regen", tmp)
        cast_before = sorted(a["agent_id"] for a in before.agents["agents"])

        # 只重生 writer 层（换一套 signals 名，但仍闭合）—— 用只产 writer 的 fake
        alt_writer = {
            "nodes": _G3_WRITER["nodes"],
            "edges": [
                {"id": "adv", "trigger": {"type": "story_advance", "signal": "proceed"}, "actions": []},
                {"id": "fin", "trigger": {"type": "story_advance", "signal": "done"}, "actions": []},
                {"id": "fail", "trigger": {"type": "story_advance", "signal": "kicked"}, "actions": []},
            ],
            "signals": {"story_advance": {"enabled": True, "valid_signals": ["proceed", "done", "kicked"]},
                        "keyword_sets": {}, "params": {}},
        }

        def writer_only_fake(system: str, user: str) -> str:
            assert "编剧" in system, "局部重生成只应调用 Writer"
            return json.dumps(alt_writer)

        regen = regenerate_writer("studio_regen", client=writer_only_fake, target_dir=tmp)
        assert regen.ok, regen.issues
        after = _load_pack_from_dir("studio_regen", tmp)
        # cast 与图骨架不变
        assert sorted(a["agent_id"] for a in after.agents["agents"]) == cast_before
        assert set(after.graph.nodes) == set(before.graph.nodes)
        # writer 层确实变了（新 signal 名进了 signals）
        assert "proceed" in after.story_advance_signals()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- G6：成本护栏 + 生成 trace ----

def test_metering_cost_guard_stops() -> None:
    import tempfile

    from agent_world.hbm_demo.tools.story_studio import BudgetExceededError, generate_full

    tmp = Path(tempfile.mkdtemp())
    try:
        # 完整流水线一轮需 3 次 LLM 调用；护栏设 2 → 超限即停
        try:
            generate_full(_GOOD_BRIEF, story_id="studio_budget", client=_routing_fake(),
                         target_dir=tmp, max_llm_calls=2)
        except BudgetExceededError:
            pass
        else:
            raise AssertionError("max_llm_calls=2 应触发 BudgetExceededError")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_metering_trace_records_calls() -> None:
    import tempfile

    from agent_world.hbm_demo.tools.story_studio import GenerationTrace, generate_full

    tmp = Path(tempfile.mkdtemp())
    try:
        trace = GenerationTrace()
        result = generate_full(_GOOD_BRIEF, story_id="studio_trace", client=_routing_fake(),
                              target_dir=tmp, trace=trace)
        assert result.ok
        assert trace.calls == 3, f"应记录 Designer/Casting/Writer 三次调用，实际 {trace.calls}"
        assert trace.total_output_chars > 0
        assert "LLM 调用 3 次" in trace.summary()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- G5：素材清单 txt ----

def test_asset_manifest_lists_all_images() -> None:
    from agent_world.hbm_demo.shared.story_pack import load_story_pack
    from agent_world.hbm_demo.tools.story_studio import render_asset_manifest

    pack = load_story_pack("canglan_sword")
    text = render_asset_manifest(pack)
    # 数据驱动：封面 + 每个地点背景 + 每个 NPC 立绘（玩家 0 不出）
    n_places = len(pack.places.get("places") or [])
    n_npcs = len([a for a in pack.agents["agents"] if int(a["agent_id"]) > 0])
    assert "封面图" in text
    assert text.count("场景背景：") == n_places
    assert text.count("角色立绘：") == n_npcs
    assert f"共需 {1 + n_places + n_npcs} 张图片" in text
    # 提示词含统一画风要求
    assert "统一画风要求" in text


def test_asset_manifest_write_to_tmp_and_safety() -> None:
    import shutil
    import tempfile

    from agent_world.hbm_demo.shared.story_pack import load_story_pack
    from agent_world.hbm_demo.tools.story_studio import write_asset_manifest
    from agent_world.hbm_demo.tools.story_studio.asset_manifest import MANIFEST_FILENAME

    pack = load_story_pack("canglan_sword")
    tmp = Path(tempfile.mkdtemp())
    try:
        path = write_asset_manifest(pack, target_dir=tmp)
        assert path.name == MANIFEST_FILENAME and path.is_file()
        assert "图片素材清单" in path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_graph_red_line() -> None:
    """story_studio 源码不得引用 kernel/seed/world_db/http（dev_logs/45 §1.2 机制级红线）。"""
    studio_dir = Path(__file__).resolve().parents[2] / "tools" / "story_studio"
    forbidden = ("core.runner.kernel", "core.runner.seed", "persistence.world_db",
                 "hbm_demo.http", "build_kernel", "seed_world", "WorldDB")
    offenders = []
    for py in studio_dir.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        for token in forbidden:
            # 只看 import 行，避免命中注释/文档里的字样
            for line in src.splitlines():
                ls = line.strip()
                if (ls.startswith("import ") or ls.startswith("from ")) and token in ls:
                    offenders.append(f"{py.name}: {ls}")
    assert not offenders, f"story_studio 触碰运行期红线 import：{offenders}"


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
    print(f"\nstory_studio G1 单测：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
