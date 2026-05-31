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

from agent_world.hbm_demo.shared.prompt_paths import story_dir
from agent_world.hbm_demo.shared.story_pack import load_story_pack
from agent_world.hbm_demo.tools.story_studio.writer import write_story_pack


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
    player = brief.get("player") or {}
    return {
        "schema_version": 1,
        "simulation_id": story_id,
        "title": brief.get("premise", story_id)[:40] if brief.get("premise") else story_id,
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
    from agent_world.hbm_demo.tools.story_studio.agents.designer import Designer
    from agent_world.hbm_demo.tools.story_studio.base_agent import StoryStudioError

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
                         ("inject_agents", "place_focus", "window_since"))
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
    from agent_world.hbm_demo.shared.story_pack import load_story_pack
    from agent_world.hbm_demo.tools.story_studio.agents.writer import Writer
    from agent_world.hbm_demo.tools.story_studio.base_agent import StoryStudioError

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
) -> CompileResult:
    """完整流水线 Designer→Casting→Writer→assemble→validate(V+X)→失败回灌重生成。

    产出**完整可运行** Story Pack（世界原语 + 控制流全齐）。client 注入，离线可测。
    可选 max_llm_calls 成本护栏 + trace 生成决策链记录（dev_logs/45 §7）。
    """
    from agent_world.hbm_demo.tools.story_studio.agents.casting import Casting
    from agent_world.hbm_demo.tools.story_studio.agents.designer import Designer
    from agent_world.hbm_demo.tools.story_studio.agents.writer import Writer
    from agent_world.hbm_demo.tools.story_studio.base_agent import StoryStudioError
    from agent_world.hbm_demo.tools.story_studio.metering import metering_client

    client = metering_client(client, max_calls=max_llm_calls, trace=trace)
    designer, casting, writer = Designer(client), Casting(client), Writer(client)
    feedback = ""
    last_issues: List[str] = []
    for _round in range(max_rounds):
        d = designer.run(brief, feedback=feedback)
        c = casting.run(brief, d, feedback=feedback)
        w = writer.run(d, c, feedback=feedback)
        sections = assemble_full_sections(brief, story_id, d, c, w)
        result = compile_pack(sections, story_id=story_id, target_dir=target_dir)
        if result.ok:
            return result
        last_issues = result.issues
        feedback = "整包校验未过：\n" + "\n".join(result.issues) + "\n请各自修正引用/结构后重新输出完整 JSON。"
    raise StoryStudioError(f"generate_full '{story_id}' 失败：{max_rounds} 轮仍未过 validate：{last_issues}")


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

    from agent_world.hbm_demo.shared.story_pack.graph import StoryGraph
    from agent_world.hbm_demo.shared.story_pack.pack import StoryPack, _OPTIONAL

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
