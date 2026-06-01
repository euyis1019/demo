"""story_studio 编排器骨架（dev_logs/45 §1.3 / §6 G1）。

职责：assemble sections → 落盘 → validate 闸门（不含 LLM 业务；agent 调用在 G2 接入）。
本切片（G1）提供「纯落盘 + 校验」骨架：给一组 sections（手写或由管理 agent 产出），
组装成 Story Pack 写盘并跑加载期 validate。Plan→Review→Revise 回路与真实 agent 流水线在 G2+。

落点固定 config/stories/<id>/；写盘走 writer.assert_safe_target 红线。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_world.drama_demo.shared.prompt_paths import story_dir
from agent_world.drama_demo.shared.story_pack import load_story_pack
from agent_world.drama_demo.tools.story_studio.writer import write_story_pack


@dataclass
class CompileResult:
    story_id: str
    target_dir: Path
    issues: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def designer_output_to_story_graph(designer: Dict[str, Any]) -> Dict[str, Any]:
    """把 DesignerOutput 骨架投影成 story_graph.yaml section（边的 trigger/actions 待 Writer 补）。"""
    return {
        "schema_version": 1,
        "initial_node": designer["initial_node"],
        "nodes": designer.get("nodes", []),
        "endings": designer.get("endings", []),
        "edges": designer.get("edges", []),
    }


def brief_to_meta(brief: Dict[str, Any], story_id: str) -> Dict[str, Any]:
    """从 brief 投影一份最小 meta（G2 骨架级；完整 clock/llm 由 G3 Casting/Writer 补）。"""
    import re as _re

    player = brief.get("player") or {}
    # 标题：优先用户给的 title；否则取 premise 的第一句（按句读/逗号断，不在词中硬截到 40 字病句）。
    premise = str(brief.get("premise") or "").strip()
    first_clause = _re.split(r"[。．.！!？?，,；;\n]", premise, 1)[0].strip() if premise else ""
    title = str(brief.get("title") or "").strip() or first_clause[:60] or story_id
    return {
        "schema_version": 1,
        "simulation_id": story_id,
        "title": title,
        "player": {
            "agent_id": 0,
            "name": player.get("identity", "玩家"),
            "role": player.get("role", "player"),
        },
    }


def generate(
    brief: Dict[str, Any],
    *,
    story_id: str,
    client: Any,
    target_dir: Optional[Path] = None,
    max_rounds: int = 3,
) -> CompileResult:
    """Plan→Review→Revise：Designer 产骨架 → validate 闸门 → 失败回灌重生成（最多 max_rounds 轮）。

    client 注入（离线测试可用 fake）。仅产出图骨架 + 最小 meta；完整世界原语（agents/places/
    relations/triggers）由 G3 Casting/Writer 接入。校验不过且轮次耗尽 → raise StoryStudioError。
    """
    from agent_world.drama_demo.tools.story_studio.agents.designer import Designer
    from agent_world.drama_demo.tools.story_studio.base_agent import StoryStudioError

    designer = Designer(client)
    feedback = ""
    last_issues: List[str] = []
    for _round in range(max_rounds):
        designer_out = designer.run(brief, feedback=feedback)
        sections = {
            "meta": brief_to_meta(brief, story_id),
            "story_graph": designer_output_to_story_graph(designer_out),
        }
        result = compile_pack(sections, story_id=story_id, target_dir=target_dir)
        if result.ok:
            return result
        last_issues = result.issues
        feedback = "上一版故事图校验未过：\n" + "\n".join(result.issues) + "\n请修正后重新输出完整 DesignerOutput JSON。"
    raise StoryStudioError(
        f"generate '{story_id}' 失败：{max_rounds} 轮仍未过 validate：{last_issues}"
    )


def _merge_by_id(base: List[Dict[str, Any]], enrich: List[Dict[str, Any]], keys) -> List[Dict[str, Any]]:
    """按 id 把 enrich 的若干键并进 base（base 顺序为准）。"""
    em = {e.get("id"): e for e in enrich}
    out: List[Dict[str, Any]] = []
    for item in base:
        merged = dict(item)
        e = em.get(item.get("id"))
        if e:
            for k in keys:
                if k in e:
                    merged[k] = e[k]
        out.append(merged)
    return out


def assemble_sections(
    meta: Dict[str, Any], designer: Dict[str, Any],
    casting: Dict[str, Any], writer: Dict[str, Any],
) -> Dict[str, Any]:
    """合并 meta + Designer(骨架) + Writer(节点/边血肉) + Casting(世界原语) → 完整 sections。"""
    nodes = _merge_by_id(designer.get("nodes", []), writer.get("nodes", []),
                         ("inject_agents", "place_focus", "scene_brief", "directions"))
    edges = _merge_by_id(designer.get("edges", []), writer.get("edges", []),
                         ("condition", "actions", "legacy_label"))
    story_graph = {
        "schema_version": 1,
        "initial_node": designer["initial_node"],
        "nodes": nodes,
        "endings": designer.get("endings", []),
        "edges": edges,
    }
    return {
        "meta": meta,
        "story_graph": story_graph,
        "places": {"places": casting.get("places", []), "coverage": casting.get("coverage", [])},
        "agents": {"agents": casting.get("agents", [])},
        "relations": {"relations": casting.get("relations", [])},
        "relation_types": {"relation_types": casting.get("relation_types", [])},
        "groups": {"groups": casting.get("groups", [])},
        "signals": writer.get("signals", {}),
    }


def _full_meta(brief: Dict[str, Any], story_id: str, casting: Dict[str, Any]) -> Dict[str, Any]:
    meta = brief_to_meta(brief, story_id)
    player_loc = next(
        (a.get("location") for a in casting.get("agents", []) if int(a.get("agent_id", -1)) == 0), None
    )
    if player_loc:
        meta["player"]["start_place"] = player_loc
    meta["clock"] = {"start_time": "09:00", "minutes_per_tick": 2}
    meta["runner"] = {"parallel_agent_decisions": True}
    meta["llm"] = brief.get("llm") or {
        "base_url": "https://api.deepseek.com", "api_key_env": "DMXAPI_KEY",
        "model": "deepseek-chat", "temperature": 0.7, "max_tokens": 500,
    }
    return meta


def assemble_full_sections(
    brief: Dict[str, Any], story_id: str, designer: Dict[str, Any],
    casting: Dict[str, Any], writer: Dict[str, Any],
) -> Dict[str, Any]:
    """从 brief 出发组装完整 sections（生成路径）。"""
    return assemble_sections(_full_meta(brief, story_id, casting), designer, casting, writer)


def _pack_to_designer(pack: Any) -> Dict[str, Any]:
    """从已加载的 StoryPack 反推 DesignerOutput 形状（供局部重生成喂下游 agent）。"""
    g = pack.graph
    return {
        "initial_node": g.initial_node,
        "nodes": [{"id": n.id, "beats_label": n.beats_label, "summary": n.summary} for n in g.nodes.values()],
        "endings": [{"id": e.id, "kind": e.kind, "summary": e.summary} for e in g.endings.values()],
        "edges": [{"id": e.id, "from": e.src, "to": e.dst} for e in g.edges],
    }


def _pack_to_casting(pack: Any) -> Dict[str, Any]:
    return {
        "agents": pack.agents.get("agents", []),
        "places": pack.places.get("places", []),
        "coverage": pack.places.get("coverage", []),
        "relations": pack.relations.get("relations", []),
        "relation_types": pack.relation_types.get("relation_types", []),
        "groups": pack.groups.get("groups", []),
    }


def regenerate_writer(
    story_id: str, *, client: Any, target_dir: Optional[Path] = None, max_rounds: int = 2,
) -> CompileResult:
    """局部重生成：固定 cast + 图骨架，只让 Writer 重产触发/注入/signals（dev_logs/45 §5.3）。

    这是最安全的局部重生（Writer 仅依赖 designer+casting，二者不动）。其余 section 原样保留。
    """
    from agent_world.drama_demo.shared.story_pack import load_story_pack
    from agent_world.drama_demo.tools.story_studio.agents.writer import Writer
    from agent_world.drama_demo.tools.story_studio.base_agent import StoryStudioError

    target = Path(target_dir) if target_dir is not None else story_dir(story_id)
    pack = load_story_pack(story_id) if target == story_dir(story_id) else _load_pack_from_dir(story_id, target)
    designer, casting, meta = _pack_to_designer(pack), _pack_to_casting(pack), pack.meta

    writer = Writer(client)
    feedback = ""
    last_issues: List[str] = []
    for _round in range(max_rounds):
        w = writer.run(designer, casting, feedback=feedback)
        sections = assemble_sections(meta, designer, casting, w)
        result = compile_pack(sections, story_id=story_id, target_dir=target)
        if result.ok:
            return result
        last_issues = result.issues
        feedback = "重生成校验未过：\n" + "\n".join(result.issues) + "\n请修正后重新输出完整 JSON。"
    raise StoryStudioError(f"regenerate_writer '{story_id}' 失败：{max_rounds} 轮仍未过：{last_issues}")


def generate_full(
    brief: Dict[str, Any], *, story_id: str, client: Any,
    target_dir: Optional[Path] = None, max_rounds: int = 3,
    max_llm_calls: Optional[int] = None, trace: Any = None,
    critic_rounds: int = 2, critic_threshold: int = 3,
) -> CompileResult:
    """完整流水线 Designer→Casting→Writer→assemble→validate(V+X)→失败回灌重生成，
    结构合法后再过 **Critic 质量门**（按叙事 rubric 评分，低分则把意见回灌定向重写 Casting/Writer）。

    产出**完整可运行**且经质量评审的 Story Pack。client 注入，离线可测。
    可选 max_llm_calls 成本护栏 + trace 生成决策链记录。critic_rounds=0 可关闭质量门（如离线 fake client）。
    """
    from agent_world.drama_demo.tools.story_studio.agents.casting import Casting
    from agent_world.drama_demo.tools.story_studio.agents.critic import Critic
    from agent_world.drama_demo.tools.story_studio.agents.designer import Designer
    from agent_world.drama_demo.tools.story_studio.agents.writer import Writer
    from agent_world.drama_demo.tools.story_studio.base_agent import StoryStudioError
    from agent_world.drama_demo.tools.story_studio.metering import metering_client

    client = metering_client(client, max_calls=max_llm_calls, trace=trace)
    designer, casting, writer = Designer(client), Casting(client), Writer(client)
    feedback = ""
    last_issues: List[str] = []
    d = c = w = None
    sections: Dict[str, Any] = {}
    result: Optional[CompileResult] = None

    # ① 结构回路：产出结构/引用合法 **且 beat 足够详细** 的整包。
    #    beat 详细度(D：scene_brief/directions 覆盖在场角色/condition 非空)只在质量门开启(critic_rounds>0)时强制，
    #    不达标连同结构违例一起回灌重生成；离线 fake-client(critic_rounds=0) 只看结构，跳过详细度门。
    structural_ok = False
    for _round in range(max_rounds):
        d = designer.run(brief, feedback=feedback)
        c = casting.run(brief, d, feedback=feedback)
        w = writer.run(d, c, brief=brief, feedback=feedback)
        sections = assemble_full_sections(brief, story_id, d, c, w)
        result = compile_pack(sections, story_id=story_id, target_dir=target_dir)
        detail_issues: List[str] = []
        if result.ok and critic_rounds > 0:
            _target = Path(target_dir) if target_dir is not None else story_dir(story_id)
            _pack = (load_story_pack(story_id) if _target == story_dir(story_id)
                     else _load_pack_from_dir(story_id, _target))
            detail_issues = _pack.validate_beat_detail()
        if result.ok and not detail_issues:
            structural_ok = True
            break
        last_issues = list(result.issues) + detail_issues
        feedback = (
            "整包未过验收：\n" + "\n".join(last_issues)
            + "\n请修正后重新输出完整 JSON；尤其每个有在场 NPC 的节点务必写出非空 scene_brief、"
            "给全部 inject_agents 各写一条 directions、每条边写一句可判定的 condition。"
        )
    if not structural_ok:
        raise StoryStudioError(f"generate_full '{story_id}' 失败：{max_rounds} 轮仍未过验收：{last_issues}")

    # ② 质量回路：Critic 按 rubric 评分，低分项把意见回灌定向重写 Casting/Writer（骨架 d 固定不动）。
    #    任一重写若破坏结构 → 回滚到上一版已合法的包并停止；评审本身报错也不阻断（保留已合法包）。
    if critic_rounds > 0:
        critic = Critic(client)
        last_good = sections
        for _q in range(critic_rounds):
            try:
                review = critic.review(brief, d, c, w)
            except Exception:  # noqa: BLE001 — 评审失败不阻断：保留已结构合法的包
                break
            scores = review.get("scores") or {}
            low = [k for k, v in scores.items() if isinstance(v, int) and v < critic_threshold]
            cfb = (review.get("casting_feedback") or "").strip()
            wfb = (review.get("writer_feedback") or "").strip()
            if not low or (not cfb and not wfb):
                break  # 质量达标 / 评审无可执行意见 → 收工
            if cfb:
                c = casting.run(brief, d, feedback="【质量评审，请据此改进角色卡，仍输出完整 JSON】\n" + cfb)
            w = writer.run(d, c, brief=brief,
                           feedback="【质量评审，请据此改进分幕，仍输出完整 JSON】\n"
                           + (wfb or "结合最新角色设定复核并加厚各幕 directions/condition。"))
            revised = assemble_full_sections(brief, story_id, d, c, w)
            r2 = compile_pack(revised, story_id=story_id, target_dir=target_dir)
            if r2.ok:
                result, last_good = r2, revised
            else:
                compile_pack(last_good, story_id=story_id, target_dir=target_dir)  # 回滚已合法包
                break

    # 设计期管理 agent 附加产物：仅在完整生成（critic_rounds>0，真实 client 的生产路径）时跑；
    # 离线 fake-client 测试关 critic 也顺带跳过。任一步失败都不阻断已结构合法的包。
    if critic_rounds > 0:
        # 新手引导：管理 agent 生成「故事背景 + 此刻可做的行为」，写进 meta.onboarding。
        try:
            from agent_world.drama_demo.tools.story_studio.onboarding import generate_onboarding

            onb = generate_onboarding(brief, d, c, client)
            _patch_meta(story_id, target_dir, "onboarding", onb)
        except Exception:  # noqa: BLE001
            pass

        # 表演须知：管理 agent 按本故事基调生成「该怎么演」的导演手册，写进 meta.acting_guide。
        # 运行期 knowledge.py 只注入这段、不再内嵌表演规则（dev_logs/43 管理 vs 演员）。
        try:
            from agent_world.drama_demo.tools.story_studio.acting_guide import generate_acting_guide

            guide = generate_acting_guide(brief, c, client)
            if guide:
                _patch_meta(story_id, target_dir, "acting_guide", guide)
        except Exception:  # noqa: BLE001
            pass

        # 属性面板：管理 agent 按故事生成可量化维度集 + 打分裁判，写进 meta.stats。
        # 运行期 f04 scoring 据此泛化打分、前端据此渲染 HUD，引擎不写死任何故事专属维度。
        try:
            from agent_world.drama_demo.tools.story_studio.stats_design import generate_stats_design

            stats = generate_stats_design(brief, c, client)
            if stats.get("dimensions"):
                _patch_meta(story_id, target_dir, "stats", stats)
        except Exception:  # noqa: BLE001
            pass

    return result


def _patch_meta(story_id: str, target_dir: Optional[Path], key: str, value: Any) -> None:
    """把管理 agent 的附加产物写进已落盘的 meta.yaml（过安全红线；均为 meta 的可选附加字段）。"""
    import yaml

    from agent_world.drama_demo.tools.story_studio.safety import assert_safe_target

    target = assert_safe_target(Path(target_dir) if target_dir is not None else story_dir(story_id))
    meta_path = target / "meta.yaml"
    if not meta_path.is_file():
        return
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    meta[key] = value
    meta_path.write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")


def compile_pack(
    sections: Dict[str, Any],
    *,
    story_id: str,
    target_dir: Optional[Path] = None,
) -> CompileResult:
    """组装 sections → 写 Story Pack → 跑 validate。返回违例（空=通过）。

    target_dir 默认 config/stories/<id>/；测试可传临时目录。写盘前过安全红线。
    """
    target = Path(target_dir) if target_dir is not None else story_dir(story_id)
    write_story_pack(sections, target)
    # 仅当写到生产落点时用标准 loader 校验；否则在该目录就地校验。
    pack = load_story_pack(story_id) if target == story_dir(story_id) else _load_pack_from_dir(story_id, target)
    return CompileResult(story_id=story_id, target_dir=target, issues=pack.validate())


def _load_pack_from_dir(story_id: str, directory: Path):
    """从任意目录加载 StoryPack（测试用；生产走 story_dir）。"""
    import yaml

    from agent_world.drama_demo.shared.story_pack.graph import StoryGraph
    from agent_world.drama_demo.shared.story_pack.pack import StoryPack, _OPTIONAL

    def _load(name: str) -> Dict[str, Any]:
        path = directory / f"{name}.yaml"
        if not path.is_file():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    meta = _load("meta")
    graph = StoryGraph.from_mapping(_load("story_graph"))
    pack = StoryPack(story_id=story_id, meta=meta, graph=graph)
    for name in _OPTIONAL:
        data = _load(name)
        if data:
            setattr(pack, name, data)
    return pack
