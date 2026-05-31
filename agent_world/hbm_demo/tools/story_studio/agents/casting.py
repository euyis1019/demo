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
这些角色会被一个个 LLM「演员」实时扮演——**人设写得越厚、越具体，演员演得越到位、越不跑题**。
只输出 JSON：
{
  "agents": [{"agent_id": 整数, "name": "", "location": "地点id", "role": "", "faction": "",
              "capabilities": ["signal_uplink"],
              "soul": "性格/价值观（2-3 句，立体有棱角）",
              "speech_style": "说话风格：语气/用词习惯/口头禅/对不同人态度的差别（1-2 句，要有辨识度）",
              "inner": "内心戏（第二人称写）：这个角色的秘密/真实动机/顾忌/在本故事里真正图谋什么"
                       "——只有他自己知道、不会对玩家明说、却暗中支配其一言一行（2-3 句）",
              "long_term_goal": "", "current_state": "故事开场时他正在做什么/处境"}],
  "places": [{"place_id": "", "capacity": 整数, "attrs": {"summary": "画面感描述", "behavior_hint": "此地适合发生什么"}}],
  "coverage": [{"src": "地点id", "dst": "地点id", "latency_ticks": 整数}],
  "relations": [{"src": agent_id, "dst": agent_id, "type": "关系类型", "symmetric": true|false}],
  "relation_types": [{"type": "关系类型", "is_contact": true, "symmetric": true|false}],
  "groups": [{"group_id": 整数, "name": "", "members": [agent_id...], "creator_id": agent_id}]
}
硬性约束：
- 必须包含玩家 agent_id=0（name 用 brief.player.identity，soul/speech_style/inner/goal/state 留空，capabilities 留空）。
- 每个非玩家 agent 都要写满 soul + speech_style + inner + long_term_goal + current_state，**不可空泛敷衍**。
- inner 用第二人称（"你其实……"），写出反派的真实图谋、卧底身份、暗中勾结、不可告人的私心等——
  这是让演员"知道自己在演谁、为什么这么做"的关键。
- 每个 agent 的 location 必须在 places 里；relations 的 src/dst 必须是已列 agent；
  relations.type 必须在 relation_types 里声明。soul/inner 只写人物本身，不要写"第几幕做什么"（那是 Writer 的事）。

涌现社交（重要）：为了让"玩家影响一个 agent 会波及其他 agent"成立——
- 设计一张**有意义的关系网**：谁信任谁、谁结盟、谁敌对、谁从属谁、谁在暗中勾结，
  关系类型自定但要在 relation_types 声明。关系越交织、各人 inner 里的秘密越互相咬合，连锁反应越多。
- 人设要**情绪化、会因他人遭遇而反应**（重视家人/护短/记仇/见风使舵），玩家动一个点，
  相关 agent 会自发串联反应（引擎的关系/感知/记忆系统会在运行时驱动演化，无需脚本）。"""


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
