"""世界规则设计（管理 agent）：按故事基调决定运行期世界开关，写进 meta.world。

目前一个开关 `npc_free_move`：**导演是否自动把「反应中的 NPC」聚到玩家面前（自动聚场）**。
注意：actor 自己按角色意图发起的 `request_move` **始终放行、与本开关无关**——任何故事里 NPC 想走都能走、
言行一致。本开关只决定「引擎导演要不要主动搬人」这一条：
- false（封闭/聚焦型）：引擎导演**不**主动搬人——孤岛庄园/密室谋杀、审讯对峙、一桌人摊牌；NPC 各守
  Casting 摆好的原位、玩家逐个走过去盘问。避免导演把反应 NPC 反复聚到玩家面前又拽回原位的「来回闪动」。
  （NPC 仍可凭自己决策走动，false 只是关掉导演自动聚场，不冻结自主移动。）
- true（开放/活世界型）：允许导演按 bert 把「该反应的 NPC」聚到玩家所在地——门派纷争、闹市江湖、潜行
  追逃、多地点奔走，制造偶遇与同场对峙。
由管理 agent 按故事判定，运行期经 scenario_adapter.is_free_move_enabled 只门控 f05 导演的 `_gather_scene`。
引擎不写死任何故事的移动策略，也不靠本开关禁止 NPC 自主移动。

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
        # 导演是否自动把「反应中的 NPC」聚到玩家面前（自动聚场）。NPC 自主移动与此无关、始终放行。
        "npc_free_move": {"type": "boolean"},
        # 一句话理由（便于审阅，不进运行期）。
        "reason": {"type": "string"},
    },
}

_SYSTEM = """你是这部互动剧的**世界设定师**。只决定一个开关 npc_free_move：**引擎导演要不要自动把
「正在对玩家做出反应的 NPC」聚到玩家所在地（自动聚场）**。

重要前提：NPC 自己按角色意图走动（request_move）在任何故事里都**始终允许**、与本开关无关——你**不是**
在决定「NPC 能不能动」，而是在决定「引擎要不要主动替你把人搬到玩家面前」。

- 选 false（封闭/聚焦型，多数盘问/密室类故事的默认）：引擎**不**主动搬人——如孤岛庄园/密室谋杀、审讯
  对峙、一桌人摊牌。NPC 各守在 Casting 摆好的原位，玩家自己走过去逐个盘问；避免导演把人反复聚到玩家
  面前又拽回原位造成「来回闪动」。注意：NPC 仍可凭自己的决定离场/走动，这不受影响。
- 选 true（开放/活世界型）：允许导演按剧情把「该反应的 NPC」聚到玩家所在地——如门派纷争、闹市江湖、
  潜行追逃、多地点奔走，制造偶遇与同场对峙、让世界更鲜活。

只输出 JSON：{"npc_free_move": true 或 false, "reason": "一句话为什么这么定（按『要不要自动聚场』来表述，
别再说成 NPC 能不能动）"}。"""


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
