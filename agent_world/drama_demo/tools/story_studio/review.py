"""人在环审阅（dev_logs/45 §5.1 / dev_logs/48）：把 Story Pack 渲染成可读概览 + 校验报告，供用户过目/微调。

纯只读、无 LLM。给出 bert（条件→反应）反应链 + 结局 + 世界原语规模 + validate(X+B) 结果。
"""

from __future__ import annotations

from typing import List

from agent_world.drama_demo.shared.story_pack import StoryPack


def render_review(pack: StoryPack) -> str:
    """渲染一份人类可读的 Story Pack 审阅报告（bert 驱动）。"""
    lines: List[str] = []
    lines.append(f"# Story Pack 审阅：{pack.story_id}")
    title = (pack.meta or {}).get("title") or ""
    if title:
        lines.append(f"  标题：{title}")
    lines.append("")

    berts = pack.berts.berts
    name = {
        int(a["agent_id"]): a.get("name", "")
        for a in pack.agents.get("agents", [])
        if "agent_id" in a
    }
    armed0 = set(pack.berts.initially_armed())

    # bert 反应链：▶ 开局上膛 / • 经前置链上膛
    lines.append(f"## bert 反应链（条件 → 反应，共 {len(berts)} 条；▶ 开局上膛）")
    for bid, b in berts.items():
        mark = "▶" if bid in armed0 else "•"
        if b.is_ending:
            end = b.ending or {}
            lines.append(f"  {mark} [结局·{end.get('kind')}] {bid}：当『{b.trigger}』→ {end.get('summary', '')}")
        else:
            tgt = name.get(int(b.target or 0)) or f"agent{b.target}"
            chain = ""
            if b.requires:
                chain += f"  ⟵需先 {b.requires}"
            if b.arms:
                chain += f"  ⟶上膛 {b.arms}"
            lines.append(f"  {mark} {bid} → {tgt}：当『{b.trigger}』→ {b.reaction}{chain}")
    lines.append("")

    # 世界原语规模
    lines.append("## 世界原语")
    lines.append(
        f"  agents={len(pack.agent_ids())}  places={len(pack.place_ids())}  "
        f"relations={len(pack.relations.get('relations', []))}  groups={len(pack.group_ids())}"
    )
    lines.append("")

    # 校验
    issues = pack.validate()
    if issues:
        lines.append(f"## ✗ 校验未通过（{len(issues)} 项）")
        for it in issues:
            lines.append(f"  {it}")
    else:
        lines.append("## ✓ 校验通过（X 跨文件引用闭合 + B bert 规则集）")
    return "\n".join(lines)
