"""属性维度设计（管理 agent）：为每个故事生成「玩家属性面板」的维度集 + 打分裁判人设。

设计意图：属性系统也要数据驱动——不同故事有不同的可量化维度（武侠：门派威望/江湖人脉；
太空惊悚：氧气/信任/理智）。由管理 agent 按故事基调生成 meta.stats，运行期 f04 scoring 据此
泛化打分、前端据此渲染 HUD，引擎不写死任何故事专属维度。

单一职责，LLM 注入，离线可测。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

STATS_DESIGN_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["judge_persona", "dimensions"],
    "properties": {
        # 打分裁判的人设/视角（第二人称对裁判说），贴本故事基调。
        "judge_persona": {"type": "string", "minLength": 16},
        # 可量化属性维度（数量由故事自决，仅留宽松上下限作护栏）。
        "dimensions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["key", "label", "initial", "description"],
                "properties": {
                    # 英文 snake_case 程序键（稳定、用于 *_delta 字段与前端 key）。
                    "key": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                    # 中文展示名（HUD 标签）。
                    "label": {"type": "string", "minLength": 1},
                    # 初始值 0-100。
                    "initial": {"type": "integer", "minimum": 0, "maximum": 100},
                    # 这个维度衡量什么（喂给裁判判分用）。
                    "description": {"type": "string", "minLength": 4},
                },
            },
        },
    },
}

_SYSTEM = """你是互动剧情的**数值策划**。为这个故事设计「玩家属性面板」：玩家每回合的发言会被裁判评估，
据此让若干可量化维度涨跌，给玩家『我的选择在影响什么』的反馈。维度要贴这个故事的核心张力与目标。

举例（仅示范思路，按本故事重写）：武侠夺嫡→门派威望/盟友信任/危险暴露；太空惊悚→氧气余量/船员信任/理智。

输出 JSON：
{
  "judge_persona": "用第二人称写给裁判：你是<这个故事>的裁判，依据玩家发言评估其在各维度的变化（贴基调）",
  "dimensions": [
    {"key": "英文snake_case程序键", "label": "中文展示名", "initial": 初始值0-100整数, "description": "这个维度衡量什么"}
  ]
}
要求：key 用稳定的英文 snake_case（如 reputation/trust/exposure）；label 用中文；
**维度数由你按这个故事的核心张力与抉择空间自决**（简单线性故事 1-2 个，复杂博弈/多目标故事 4-7 个，不为凑数硬加）；
贴本故事的人物/目标/悬念，别照搬示例、别写成通用空话。只输出 JSON。"""


def _build_user(brief: Dict[str, Any], casting: Dict[str, Any]) -> str:
    agents = [
        {"name": a.get("name"), "role": a.get("role")}
        for a in (casting.get("agents") or [])
        if int(a.get("agent_id", -1)) > 0
    ]
    return (
        "故事 brief：\n" + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\n登场角色：" + json.dumps(agents, ensure_ascii=False)
        + "\n玩家：" + json.dumps(brief.get("player") or {}, ensure_ascii=False)
    )


def _sanitize(out: Dict[str, Any]) -> Dict[str, Any]:
    """去重 key、补默认、夹取范围——保证落库的 meta.stats 干净可用。"""
    seen: set[str] = set()
    dims: List[Dict[str, Any]] = []
    for d in out.get("dimensions") or []:
        key = re.sub(r"[^a-z0-9_]", "", str(d.get("key") or "").lower()) or f"stat{len(dims)}"
        if key in seen:
            continue
        seen.add(key)
        dims.append({
            "key": key,
            "label": str(d.get("label") or key),
            "initial": max(0, min(100, int(d.get("initial", 0) or 0))),
            "description": str(d.get("description") or ""),
        })
    return {"judge_persona": str(out.get("judge_persona") or "").strip(), "dimensions": dims}


def generate_stats_design(
    brief: Dict[str, Any], casting: Dict[str, Any], client: LLMClient,
) -> Dict[str, Any]:
    """产出 {judge_persona, dimensions:[{key,label,initial,description}]}。失败由调用方吞掉不阻断生成。"""
    out = call_json_with_schema(
        client, system=_SYSTEM, user=_build_user(brief, casting),
        schema=STATS_DESIGN_SCHEMA, label="stats_design",
    )
    return _sanitize(out)
