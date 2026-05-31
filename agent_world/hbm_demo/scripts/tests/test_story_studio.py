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


def test_import_graph_red_line() -> None:
    """story_studio 源码不得引用 kernel/seed/world_db/http（dev_logs/45 §1.2 机制级红线）。"""
    studio_dir = Path(__file__).resolve().parents[2] / "tools" / "story_studio"
    forbidden = ("core.runner.kernel", "core.runner.seed", "persistence.world_db",
                 "hbm_demo.http", "build_kernel", "seed_world", "WorldDB")
    offenders = []
    for py in studio_dir.glob("*.py"):
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
