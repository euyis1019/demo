#!/usr/bin/env python3
"""story_studio 离线门禁单测——覆盖 **bert（条件→反应）生成流水线**。

新流水线（generate_full）：
  ① Casting(client).run(brief) —— brief → 世界原语（agents/places/relations/...）
  ② BertDesigner(client).run(brief, casting) —— brief + cast → {"berts":[...]}（条件→反应规则集，含结局 bert）
  ③ assemble_full_sections → sections（meta/places/agents/relations/relation_types/groups/**berts**；无 story_graph、无 signals）
  ④ compile_pack 落盘 + pack.validate()（含 bert 的 B 系列校验 + 跨文件引用闭合）
  ⑤ critic_rounds>0 时再过 Critic(client).review(brief, casting, bert_design)

退役了 Designer / Writer / story_graph，剧情结构改由 bert 承载。本测试不再 import 任何已删符号。
纯离线：LLM 客户端用 fake（按 system prompt 关键词路由），不连网络/key；写盘只用临时目录。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from agent_world.drama_demo.shared.story_pack.bert import BertSet
from agent_world.drama_demo.tools.story_studio import (
    BERT_OUTPUT_SCHEMA,
    BertDesigner,
    BudgetExceededError,
    Casting,
    Critic,
    GenerationTrace,
    StoryStudioError,
    StoryStudioSafetyError,
    assemble_full_sections,
    assemble_sections,
    assert_safe_target,
    brief_to_meta,
    call_json_with_schema,
    compile_pack,
    generate_full,
    render_review,
    validate_against,
    validate_brief,
)
from agent_world.drama_demo.tools.story_studio.orchestrator import _load_pack_from_dir

# ---- 共享 fixtures（schema 都过，可直接用作 _CASTING / _BERT 基线）----

_GOOD_BRIEF = {
    "premise": "测试世界",
    "player": {"identity": "外来者", "role": "player", "is_outsider": True},
    "characters": [{"name": "甲", "faction": "f1"}],
}

_CASTING = {
    "agents": [
        {"agent_id": 0, "name": "调查员", "location": "hall", "capabilities": [],
         "soul": "", "speech_style": "", "inner": "", "long_term_goal": "", "current_state": ""},
        {"agent_id": 1, "name": "守门人", "location": "hall", "capabilities": ["signal_uplink"],
         "soul": "严谨刻板的老门房，把守门看得比命重，认死理不通融",
         "speech_style": "话少、爱用命令句、对生人板着脸",
         "speech_samples": ["站住，这个点儿不许进。", "规矩就是规矩，别跟我废话。"],
         "inner": "你收过一笔贿赂答应今夜放某人进来，正提心吊胆怕被撞破",
         "long_term_goal": "守好门别出事，别让收贿的事败露",
         "current_state": "在大厅值夜班，心神不宁"},
    ],
    "places": [{"place_id": "hall", "capacity": 5, "attrs": {"summary": "昏暗的大厅，只有一盏值夜灯"}}],
    "coverage": [{"src": "hall", "dst": "hall", "latency_ticks": 0}],
    "relations": [], "relation_types": [], "groups": [],
}

_BERT = {
    "berts": [
        # 开局非结局入口：配 hint（满足 [B12]）；arms 串后续。
        {"id": "crack", "trigger": "玩家逼问守门人是否收了贿赂并施压", "target": 1,
         "hint": "守门人收钱时眼神躲闪——抓住这点逼一逼，他未必扛得住。",
         "reaction": "心虚动摇，支吾着承认收过钱", "place": "hall", "arms": ["good_end"]},
        # 结局均串在反应链末端（requires 非空，满足 [B11]）：crack 之后才走得到两种收场；各配收场 hint（满足 [B13]）。
        {"id": "good_end", "trigger": "玩家答应替他保守秘密换他配合", "requires": ["crack"],
         "hint": "他已松口——你可以答应替他保守秘密，换一条进去的路，就此了结。",
         "ending": {"kind": "good", "summary": "守门人放你进去并供出买通他的人"}},
        {"id": "bad_end", "trigger": "玩家当众揭发守门人受贿", "requires": ["crack"],
         "hint": "或者当众把他受贿的事抖出来——痛快，但未必有好下场。",
         "ending": {"kind": "bad", "summary": "事情闹大，你被乱棍赶出"}},
    ]
}

_CRITIC_DIMS = ("character_depth", "voice_distinct", "subtext_drama", "player_agency", "plot_tension")
_CRITIC_PASS = {
    "scores": {k: 4 for k in _CRITIC_DIMS},
    "casting_feedback": "", "bert_feedback": "", "summary": "不错",
}


def _routing_fake(casting=None, bert=None, critic=None):
    """按 system prompt 关键词把 LLM 调用路由到对应 agent 的固定输出。

    关键：必须**先判 Critic**（唯一标记『叙事总监』），因为 Critic 的 system 也含子串 'bert'
    （『某条 bert 反应』），若先判 bert 会把评审误路由成 bert。其余各 agent 标记互斥：
    『反应设计师』唯 BertDesigner 有，『选角/世界搭建』唯 Casting 有。附加产物生成器（onboarding 等）
    不含任何标记 → 落到 fallback 返回 '{}'（orchestrator 对其 try/except 容错，不影响主流程）。
    """
    c = casting if casting is not None else _CASTING
    b = bert if bert is not None else _BERT
    cr = critic if critic is not None else _CRITIC_PASS

    def fake(system: str, user: str) -> str:
        if "叙事总监" in system:  # Critic 的唯一专属标记（其它 agent 的 system 都没有）
            if cr is None:
                raise AssertionError("本测试不应调用 Critic")
            return json.dumps(cr)
        if "反应设计师" in system or "bert" in system.lower():
            return json.dumps(b)
        if "选角" in system or "世界搭建" in system:
            return json.dumps(c)
        return "{}"  # 附加产物生成器：返回空 dict，orchestrator 容错跳过

    return fake


# ---- 保留：base_agent 生成→校验→重试 ----

def test_base_agent_generate_validate_retry() -> None:
    # fake client：第一次返回非法(空 berts)，第二次返回合法 → 重试后成功
    calls = {"n": 0}

    def flaky_client(system: str, user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"berts": []})  # minItems=1，schema 不过
        return json.dumps(_BERT)

    out = call_json_with_schema(
        flaky_client, system="sys", user="设计 bert", schema=BERT_OUTPUT_SCHEMA, label="bert_designer"
    )
    assert {b["id"] for b in out["berts"]} == {"crack", "good_end", "bad_end"} and calls["n"] == 2

    # 始终非法 → 重试耗尽抛错
    def bad_client(system: str, user: str) -> str:
        return "not json at all"

    try:
        call_json_with_schema(bad_client, system="s", user="u", schema=BERT_OUTPUT_SCHEMA)
    except StoryStudioError:
        pass
    else:
        raise AssertionError("始终非法应抛 StoryStudioError")


# ---- 保留：brief schema ----

def test_brief_schema_accepts_and_rejects() -> None:
    assert validate_brief(_GOOD_BRIEF) == []
    bad = {"premise": "缺 player"}
    issues = validate_brief(bad)
    assert any("player" in it for it in issues), issues
    bad2 = {"player": {"identity": "x"}}  # 缺 role
    assert validate_brief(bad2), "缺 role 应报错"


# ---- 保留：安全红线（拒 sim/ + 源码目录）----

def test_safety_rejects_sim_and_source() -> None:
    drama_root = Path(__file__).resolve().parents[2]  # .../drama_demo
    for forbidden in (drama_root / "sim" / "x", drama_root / "core" / "x", drama_root / "features" / "x"):
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


# ---- 改写：用 bert sections 编 pack（compile_pack + 新 assemble_sections）----

def test_compile_writes_valid_bert_pack() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        meta = brief_to_meta(_GOOD_BRIEF, "studio_selftest")
        sections = assemble_sections(meta, _CASTING, _BERT)
        result = compile_pack(sections, story_id="studio_selftest", target_dir=tmp)
        assert result.ok, f"bert 包应过 validate，却报：{result.issues}"
        # berts.yaml 落了盘；不产 story_graph.yaml / signals.yaml（剧情由 bert 驱动）
        assert (tmp / "berts.yaml").is_file()
        assert (tmp / "meta.yaml").is_file()
        assert (tmp / "agents.yaml").is_file()
        assert not (tmp / "story_graph.yaml").exists(), "新流水线不应产 story_graph.yaml"
        assert not (tmp / "signals.yaml").exists(), "新流水线不应产 signals.yaml"
        # 就地加载复核：validate 干净，berts 有内容
        pack = _load_pack_from_dir("studio_selftest", tmp)
        assert pack.validate() == []
        assert set(pack.berts.berts) == {"crack", "good_end", "bad_end"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_compile_rejects_bert_target_missing_agent() -> None:
    """bert target 指向不存在的 agent → validate 应报 [B2]。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        bad_bert = {
            "berts": [
                {"id": "x", "trigger": "玩家逼问他", "target": 99, "reaction": "他承认"},  # 99 不在 cast
                {"id": "e", "trigger": "收场", "ending": {"kind": "good", "summary": "结束"}},
            ]
        }
        meta = brief_to_meta(_GOOD_BRIEF, "studio_bad_target")
        sections = assemble_sections(meta, _CASTING, bad_bert)
        result = compile_pack(sections, story_id="studio_bad_target", target_dir=tmp)
        assert not result.ok and any(it.startswith("[B2]") for it in result.issues), result.issues
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_compile_rejects_bert_without_ending() -> None:
    """缺结局 bert → validate 应报 [B7]。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        no_ending = {"berts": [{"id": "x", "trigger": "玩家逼问他", "target": 1, "reaction": "他承认"}]}
        meta = brief_to_meta(_GOOD_BRIEF, "studio_no_ending")
        sections = assemble_sections(meta, _CASTING, no_ending)
        result = compile_pack(sections, story_id="studio_no_ending", target_dir=tmp)
        assert not result.ok and any(it.startswith("[B7]") for it in result.issues), result.issues
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- 新增：bert 数据模型 / 设计师直测 ----

def test_bertset_validate_catches_bad_examples() -> None:
    # target 指向不存在 agent → [B2]
    bad_target = BertSet.from_mapping({"berts": [
        {"id": "x", "trigger": "t", "target": 99, "reaction": "r"},
        {"id": "e", "trigger": "t", "ending": {"kind": "good", "summary": "s"}},
    ]})
    assert any(it.startswith("[B2]") for it in bad_target.validate(agent_ids={0, 1}, place_ids={"hall"}))

    # 缺结局 bert → [B7]
    no_ending = BertSet.from_mapping({"berts": [{"id": "x", "trigger": "t", "target": 1, "reaction": "r"}]})
    assert any(it.startswith("[B7]") for it in no_ending.validate(agent_ids={0, 1}))

    # 非结局 bert 缺 reaction/target → [B4]/[B5]；引用不存在 bert → [B1]
    missing = BertSet.from_mapping({"berts": [
        {"id": "x", "trigger": "t", "requires": ["ghost"]},  # ghost 不存在 + 缺 reaction/target
        {"id": "e", "trigger": "t", "ending": {"kind": "bad", "summary": "s"}},
    ]})
    issues = missing.validate(agent_ids={0, 1})
    assert any(it.startswith("[B1]") for it in issues), issues
    assert any(it.startswith("[B4]") for it in issues), issues
    assert any(it.startswith("[B5]") for it in issues), issues

    # 干净 bert 集 → 无违例
    good = BertSet.from_mapping(_BERT)
    assert good.validate(agent_ids={0, 1}, place_ids={"hall"}) == []


def test_bert_designer_output_passes_schema() -> None:
    """BertDesigner(fake).run(brief, casting) 的产物过 BERT_OUTPUT_SCHEMA。"""
    def fake(system: str, user: str) -> str:
        assert "反应设计师" in system or "bert" in system.lower(), "BertDesigner 的 system 应含 bert 标记"
        return json.dumps(_BERT)

    out = BertDesigner(fake).run(_GOOD_BRIEF, _CASTING)
    assert validate_against(out, BERT_OUTPUT_SCHEMA, label="bert_designer") == []
    assert {b["id"] for b in out["berts"]} == {"crack", "good_end", "bad_end"}


def test_casting_run_takes_only_brief() -> None:
    """Casting.run 现在只收 brief（不再有 designer 参数）。"""
    def fake(system: str, user: str) -> str:
        assert "选角" in system or "世界搭建" in system
        return json.dumps(_CASTING)

    out = Casting(fake).run(_GOOD_BRIEF)
    assert {a["agent_id"] for a in out["agents"]} == {0, 1}


# ---- 改写：完整流水线 generate_full ----

def test_generate_full_produces_valid_bert_pack() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        result = generate_full(_GOOD_BRIEF, story_id="studio_full", client=_routing_fake(),
                               target_dir=tmp, max_rounds=2, critic_rounds=0)
        assert result.ok, f"完整包应过 V+X+B 校验：{result.issues}"
        # 世界原语 + berts 都落了盘；**不含** story_graph.yaml / signals.yaml
        for f in ("meta", "places", "agents", "relations", "relation_types", "groups", "berts"):
            assert (tmp / f"{f}.yaml").is_file(), f"缺 {f}.yaml"
        assert not (tmp / "story_graph.yaml").exists(), "新流水线不应产 story_graph.yaml"
        assert not (tmp / "signals.yaml").exists(), "新流水线不应产 signals.yaml"
        # 就地加载复核：berts 有内容、validate 干净、含一好一坏两个结局
        pack = _load_pack_from_dir("studio_full", tmp)
        assert pack.berts.berts, "pack.berts.berts 应有内容"
        assert pack.validate() == []
        endings = {bid: b.ending["kind"] for bid, b in pack.berts.berts.items() if b.is_ending}
        assert set(endings.values()) == {"good", "bad"}, endings
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_generate_full_critic_revise_loop() -> None:
    """Critic 第一次低分 + casting_feedback → 触发 Casting/BertDesigner 定向重写；第二次达标 → 停。"""
    calls = {"casting": 0, "bert": 0, "critic": 0}

    def fake(system: str, user: str) -> str:
        if "叙事总监" in system:
            calls["critic"] += 1
            if calls["critic"] == 1:  # 低分 → 触发重写
                return json.dumps({"scores": {**{k: 4 for k in _CRITIC_DIMS}, "character_depth": 2},
                                   "casting_feedback": "把守门人的 inner 写得更具体",
                                   "bert_feedback": "", "summary": "需改"})
            return json.dumps(_CRITIC_PASS)  # 达标 → 停
        if "反应设计师" in system or "bert" in system.lower():
            calls["bert"] += 1
            return json.dumps(_BERT)
        if "选角" in system or "世界搭建" in system:
            calls["casting"] += 1
            return json.dumps(_CASTING)
        return "{}"  # 附加产物生成器（critic_rounds>0 才跑）—— 返回空 dict，orchestrator 容错

    tmp = Path(tempfile.mkdtemp())
    try:
        result = generate_full(_GOOD_BRIEF, story_id="studio_critic", client=fake,
                               target_dir=tmp, critic_rounds=2)
        assert result.ok, result.issues
        assert calls["critic"] == 2, f"应评审两次（低分→重写→达标），实际 {calls['critic']}"
        # 低分回灌应触发 Casting + BertDesigner 各重写一次（结构轮 1 次 + 评审轮 1 次 = 2 次）
        assert calls["casting"] == 2, f"低分应触发 Casting 重写一次（共 2 次），实际 {calls['casting']}"
        assert calls["bert"] == 2, f"低分应触发 BertDesigner 重写一次（共 2 次），实际 {calls['bert']}"
        # bert_feedback 回灌也能跑通：最终包仍合法
        pack = _load_pack_from_dir("studio_critic", tmp)
        assert pack.validate() == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_generate_full_raises_after_max_rounds() -> None:
    """BertDesigner 始终产「缺结局」的非法集 → 结构回路耗尽后抛 StoryStudioError。"""
    bad_bert = {"berts": [{"id": "x", "trigger": "玩家逼问", "target": 1, "reaction": "他承认"}]}  # 无结局 → [B7]

    tmp = Path(tempfile.mkdtemp())
    try:
        generate_full(_GOOD_BRIEF, story_id="studio_fail",
                      client=_routing_fake(bert=bad_bert),
                      target_dir=tmp, max_rounds=2, critic_rounds=0)
    except StoryStudioError:
        pass
    else:
        raise AssertionError("始终缺结局应在轮次耗尽后抛 StoryStudioError")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- 保留：人在环 review 渲染 ----

def _fake_pack(tmp: Path, story_id: str = "studio_synth"):
    """离线用 fake 客户端生成一个完整合法 bert Story Pack 到 tmp 并加载。
    不绑定任何已落盘故事，纯靠管理 agent 流水线现造一个包来验。"""
    generate_full(_GOOD_BRIEF, story_id=story_id, client=_routing_fake(), target_dir=tmp,
                  max_rounds=2, critic_rounds=0)
    return _load_pack_from_dir(story_id, tmp)


def test_review_renders_pack() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        pack = _fake_pack(tmp, "studio_review")
        text = render_review(pack)
        assert "Story Pack 审阅：studio_review" in text
        assert "✓ 校验通过" in text  # 合法包应渲染为校验通过
        # bert 驱动包无 story_graph，故走空图分支（initial_node='' / 无图结局）—— 这是预期
        assert pack.graph.initial_node == "" and not pack.graph.endings
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- 改写：成本护栏 + 生成 trace（调用数 = Casting + BertDesigner = 2/轮，无 Designer/Writer）----

def test_metering_cost_guard_stops() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        # 一轮结构回路需 2 次 LLM 调用（Casting + BertDesigner）；护栏设 1 → 超限即停
        try:
            generate_full(_GOOD_BRIEF, story_id="studio_budget", client=_routing_fake(),
                          target_dir=tmp, max_llm_calls=1, critic_rounds=0)
        except BudgetExceededError:
            pass
        else:
            raise AssertionError("max_llm_calls=1 应触发 BudgetExceededError")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_metering_trace_records_calls() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        trace = GenerationTrace()
        result = generate_full(_GOOD_BRIEF, story_id="studio_trace", client=_routing_fake(),
                               target_dir=tmp, trace=trace, critic_rounds=0)
        assert result.ok
        assert trace.calls == 2, f"应记录 Casting/BertDesigner 两次调用，实际 {trace.calls}"
        assert trace.total_output_chars > 0
        assert "LLM 调用 2 次" in trace.summary()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- 保留：import 图红线 ----

def test_import_graph_red_line() -> None:
    """story_studio 源码不得引用 kernel/seed/world_db/http（机制级红线）。"""
    studio_dir = Path(__file__).resolve().parents[2] / "tools" / "story_studio"
    forbidden = ("core.runner.kernel", "core.runner.seed", "persistence.world_db",
                 "drama_demo.http", "build_kernel", "seed_world", "WorldDB")
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
    print(f"\nstory_studio bert 流水线单测：{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
