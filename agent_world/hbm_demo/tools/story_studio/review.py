"""人在环审阅（dev_logs/45 §5.1）：把 Story Pack 渲染成可读概览 + 校验报告，供用户过目/微调。

纯只读、无 LLM。给出 ASCII 故事图（节点→边→结局）+ 世界原语规模 + validate(V+X) 结果。
"""

from __future__ import annotations

from typing import List

from agent_world.hbm_demo.shared.story_pack import StoryPack


def render_review(pack: StoryPack) -> str:
    """渲染一份人类可读的 Story Pack 审阅报告。"""
    g = pack.graph
    lines: List[str] = []
    lines.append(f"# Story Pack 审阅：{pack.story_id}")
    title = (pack.meta or {}).get("title") or ""
    if title:
        lines.append(f"  标题：{title}")
    lines.append("")

    # 故事图：按拓扑序列出节点 + 其出边
    lines.append("## 故事图（节点 → 边[trigger摘要] → 去向）")
    try:
        order = g.topological_sort()
    except Exception:  # noqa: BLE001
        order = list(g.nodes)
    for nid in order:
        node = g.nodes[nid]
        marker = "▶" if nid == g.initial_node else "•"
        inj = f" inject={node.inject_agents}" if node.inject_agents else ""
        loc = f" @{node.place_focus}" if node.place_focus else ""
        lines.append(f"  {marker} {nid} [{node.beats_label}]{loc}{inj}")
        for edge, dst in g.get_children(nid):
            kind = "结局" if g.is_ending(dst) else "节点"
            lines.append(f"      └─({edge.id}: {_trigger_brief(edge.trigger)})→ {dst} [{kind}]")
    lines.append("")

    # 结局
    lines.append("## 结局")
    for eid, ending in g.endings.items():
        reachable = "✓可达" if eid in g.get_reachable_endings() else "✗不可达"
        lines.append(f"  - {eid} [{ending.kind}] {reachable} — {ending.summary}")
    lines.append("")

    # 世界原语规模
    lines.append("## 世界原语")
    lines.append(
        f"  agents={len(pack.agent_ids())}  places={len(pack.place_ids())}  "
        f"relations={len(pack.relations.get('relations', []))}  "
        f"groups={len(pack.group_ids())}  "
        f"signals={len(pack.story_advance_signals())} 信号 / {len(pack.keyword_set_names())} 关键词集"
    )
    lines.append("")

    # 路径枚举
    paths = g.enumerate_all_paths()
    lines.append(f"## 可玩路径（{len(paths)} 条）")
    for p in paths:
        lines.append("  " + " → ".join(p))
    lines.append("")

    # 校验
    issues = pack.validate()
    if issues:
        lines.append(f"## ✗ 校验未通过（{len(issues)} 项）")
        for it in issues:
            lines.append(f"  {it}")
    else:
        lines.append("## ✓ 校验通过（V 结构 + X 跨文件引用闭合）")
    return "\n".join(lines)


def _trigger_brief(trigger: dict) -> str:
    """把 trigger 树压成一行摘要。"""
    if not isinstance(trigger, dict):
        return "?"
    if "any_of" in trigger:
        return " | ".join(_trigger_brief(t) for t in trigger.get("any_of") or [])
    if "all_of" in trigger:
        return " & ".join(_trigger_brief(t) for t in trigger.get("all_of") or [])
    t = trigger.get("type", "?")
    if t == "story_advance":
        return f"signal:{trigger.get('signal')}"
    if t in ("rdc_keyword", "f2f_keyword"):
        return f"{t}:{trigger.get('keyword_set')}"
    if t == "rdc_pair":
        return f"rdc:{trigger.get('sender')}→{trigger.get('recipient')}"
    if t == "timeout":
        return f"timeout:{trigger.get('gte_ref')}"
    return str(t)
