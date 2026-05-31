"""Casting 管理 agent（dev_logs/45 §3.2）：brief + 故事图骨架 → 世界原语。

单一能力：定角色花名册（含玩家 agent 0）、舞台地点、初始关系网/关系类型、群组。
不写"第几幕做什么"（那是 Writer 的 agent_behaviors）。LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import CASTING_OUTPUT_SCHEMA
from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是选角 + 世界搭建师。根据故事 brief 与故事图骨架，产出世界原语。
只输出 JSON：
{
  "agents": [{"agent_id": 整数, "name": "", "location": "地点id", "role": "", "faction": "",
              "capabilities": ["signal_uplink"], "soul": "人格(只写性格/价值观)",
              "long_term_goal": "", "current_state": "初始状态"}],
  "places": [{"place_id": "", "capacity": 整数, "attrs": {"summary": "", "behavior_hint": ""}}],
  "coverage": [{"src": "地点id", "dst": "地点id", "latency_ticks": 整数}],
  "relations": [{"src": agent_id, "dst": agent_id, "type": "关系类型", "symmetric": true|false}],
  "relation_types": [{"type": "关系类型", "is_contact": true, "symmetric": true|false}],
  "groups": [{"group_id": 整数, "name": "", "members": [agent_id...], "creator_id": agent_id}]
}
硬性约束：
- 必须包含玩家 agent_id=0（name 用 brief.player.identity，soul/goal/state 留空，capabilities 留空）。
- 每个 agent 的 location 必须在 places 里；relations 的 src/dst 必须是已列 agent；
  relations.type 必须在 relation_types 里声明。
- soul 只写人格/价值观，不要写"第几幕做什么"。"""


def _build_user_prompt(brief: Dict[str, Any], designer: Dict[str, Any]) -> str:
    return (
        "故事 brief：\n" + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\n故事图骨架：\n" + json.dumps(designer, ensure_ascii=False, indent=2)
    )


class Casting:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def run(self, brief: Dict[str, Any], designer: Dict[str, Any], *, feedback: str = "") -> Dict[str, Any]:
        user = _build_user_prompt(brief, designer)
        if feedback:
            user += f"\n\n[上一版校验未过，请修正后重新输出完整 JSON]\n{feedback}"
        return call_json_with_schema(
            self._client, system=_SYSTEM, user=user, schema=CASTING_OUTPUT_SCHEMA, label="casting"
        )
