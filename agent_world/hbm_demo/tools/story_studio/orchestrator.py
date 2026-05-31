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
