"""世界规则设计（管理 agent）：按故事基调决定运行期世界开关，写进 meta.world。

目前一个开关：**NPC 是否可凭自己决策在地点间走动（自主移动）**。
- false（守在原地）：封闭/聚焦型故事——孤岛庄园/密室谋杀、审讯对峙、一桌人摊牌；玩家需逐个上门
  盘问、信息集中在固定的人与地点，NPC 乱走会打断盘问、让线索散掉。
- true（自主走动）：开放/活世界型故事——门派纷争、闹市江湖、潜行追逃、多地点奔走；让 NPC 按
  自己的目的走动会让世界更鲜活、制造偶遇与变数。
由管理 agent 按故事判定，运行期 dispatcher（经 scenario_adapter.is_free_move_enabled）据此放行/抑制
agent 的 request_move。引擎不写死任何故事的移动策略。

单一职责，LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

WORLD_RULES_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["npc_free_move"],
    "properties": {
        # NPC 是否可凭自己决策在地点间走动（自主移动）。
        "npc_free_move": {"type": "boolean"},
        # 一句话理由（便于审阅，不进运行期）。
        "reason": {"type": "string"},
    },
}

_SYSTEM = """你是这部互动剧的**世界设定师**。判断这个故事更适合哪种 NPC 行为模式——只决定一个开关：
NPC 能不能凭自己的决策在不同地点间走动（自主移动）。

- 选 false（NPC 守在原地）：故事是**封闭/聚焦**型——如孤岛庄园/密室谋杀、审讯对峙、一桌人摊牌，
  玩家需要逐个上门盘问、信息集中在固定的人和地点；NPC 乱走会打断盘问、让线索散掉。
- 选 true（NPC 自主走动）：故事是**开放/活世界**型——如门派纷争、闹市江湖、潜行追逃、多地点奔走，
  让 NPC 按自己的目的走动会让世界更鲜活、制造偶遇与变数。

只输出 JSON：{"npc_free_move": true 或 false, "reason": "一句话为什么这么定"}。"""


def _build_user(brief: Dict[str, Any], casting: Dict[str, Any]) -> str:
    places = [p.get("place_id") for p in (casting.get("places") or [])]
    n_agents = len([a for a in (casting.get("agents") or []) if int(a.get("agent_id", -1)) > 0])
    head = {k: brief.get(k) for k in ("premise", "tone") if brief.get(k)}  # schema 只有 premise/tone
    return (
        "故事 brief：\n" + json.dumps(head, ensure_ascii=False, indent=2)
        + f"\n\n登场角色数：{n_agents}；地点数：{len(places)}；地点：" + json.dumps(places, ensure_ascii=False)
    )


def generate_world_rules(
    brief: Dict[str, Any], casting: Dict[str, Any], client: LLMClient,
) -> Dict[str, Any]:
    """产出 {npc_free_move, reason}。失败由 call_json_with_schema 抛错，调用方吞掉不阻断生成。"""
    out = call_json_with_schema(
        client, system=_SYSTEM, user=_build_user(brief, casting),
        schema=WORLD_RULES_SCHEMA, label="world_rules",
    )
    return {
        "npc_free_move": bool(out.get("npc_free_move", False)),
        "reason": str(out.get("reason") or "").strip(),
    }
