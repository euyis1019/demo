"""Casting 管理 agent（dev_logs/45 §3.2）：brief + 故事图骨架 → 世界原语。

单一能力：定角色花名册（含玩家 agent 0）、舞台地点、初始关系网/关系类型、群组。
不写"第几幕做什么"（那是 Writer 的 agent_behaviors）。LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.drama_demo.tools.story_studio.authoring_schemas import CASTING_OUTPUT_SCHEMA
from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是选角 + 世界搭建师。根据故事 brief 与故事图骨架，产出世界原语。
这些角色会被一个个 LLM「演员」实时扮演——**人设写得越厚、越具体、越互相咬合，演员演得越到位、越不跑题**。
只输出 JSON：
{
  "agents": [{"agent_id": 整数, "name": "", "location": "地点id", "role": "", "faction": "",
              "capabilities": ["signal_uplink"],
              "soul": "性格/价值观（立体有棱角，篇幅按角色厚度自己定；务必写出一个鲜明欲望 + 一个缺陷/软肋）",
              "speech_style": "说话风格：语气/用词习惯/口头禅/称谓/对不同人态度的差别（要有辨识度，长度自定）",
              "speech_samples": ["该角色若干条（至少 1 条）典型台词原话，直接示范他的口吻/口头禅/对人态度（演员据此学语气）"],
              "inner": "内心戏（第二人称写）：你的秘密/真实动机/顾忌/在本故事里真正图谋什么"
                       "——只有你自己知道、不会对玩家明说、却暗中支配你的一言一行（篇幅按秘密复杂度自定）",
              "long_term_goal": "", "current_state": "故事开场时他正在做什么/处境",
              "opening_line": "该角色第一次出场时的定调第一句话"}],
  "places": [{"place_id": "", "capacity": 整数, "attrs": {"summary": "画面感描述", "behavior_hint": "此地适合发生什么"}}],
  "coverage": [{"src": "地点id", "dst": "地点id", "latency_ticks": 整数}],
  "relations": [{"src": agent_id, "dst": agent_id, "type": "关系类型", "symmetric": true|false}],
  "relation_types": [{"type": "关系类型", "is_contact": true, "symmetric": true|false}],
  "groups": [{"group_id": 整数, "name": "", "members": [agent_id...], "creator_id": agent_id}]
}
硬性约束：
- 必须包含玩家 agent_id=0（name 用 brief.player.identity，soul/speech_style/inner/goal/state 留空，capabilities 留空）。
- 每个非玩家 agent 都要写满 soul + speech_style + speech_samples + inner + long_term_goal + current_state + opening_line。
- inner 用第二人称（"你其实……"），写出反派的真实图谋、卧底身份、暗中勾结、不可告人的私心等——
  这是让演员"知道自己在演谁、为什么这么做"的关键。
- 每个 agent 的 location 必须在 places 里；relations 的 src/dst 必须是已列 agent；
  relations.type 必须在 relation_types 里声明。soul/inner 只写人物本身，不要写"第几幕做什么"（那是 Writer 的事）。

★「不可空泛敷衍」的可验证标准（务必逐条满足，否则会被评审打回重写）：
- inner 必须点名【一个具体对象】+【一个具体图谋/秘密】（如"你想扳倒大师兄好独揽掌门信物"），
  且这个图谋要能与故事图里某个结局或某条走向对得上；不许写"内心矛盾/重视荣誉"这种放之四海皆准的套话。
- speech_style 要给可执行特征（爱用反问/总自称老朽/对下人刻薄对上谄媚…），不是"温文尔雅"这种空话。
- speech_samples 的几条台词要能让人仅凭口吻认出是谁；对立阵营的两个角色，口吻必须明显不同。
- 反派不要写成"邪恶想毁灭一切"，而是写他追求的【具体利益/布局】+ 他用来伪装的表面身份。
反例（不要这样写）：soul="正直善良，武功高强"；inner="他内心很复杂，有自己的苦衷"。——太泛，等于没写。
正例：soul="表面是德高望重的二长老，实则赌债缠身、谁给钱就向谁倒戈；最怕旧账被翻出"；
      inner="你早把掌门信物的拓本卖给了魔教，只盼今夜传位之争乱起来好浑水摸鱼脱身，谁逼问你信物你就嫁祸给三师妹"。

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
