"""Critic 管理 agent：结构合法后的「质量门」——按叙事 rubric 给整包草稿打分并给针对性修改意见。

研究依据（dev_logs 调研）：生成→按 rubric 批评→定向重写的小循环，质量显著优于一次成稿
（CritiqueLLM / ProTeGi 文本梯度）。本 agent 只评分 + 产可执行 feedback，是否需要重写由
orchestrator 按阈值决定，沿用现有 feedback 回灌通路重生成 Casting/Writer。单一职责，LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import CRITIC_OUTPUT_SCHEMA
from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是一位严格的叙事总监 + 角色扮演评审。下面是一个互动剧情「Story Pack 草稿」
（结构已合法）。这些角色会被 LLM「演员」实时扮演、由 LLM「导演」按玩家对话推进剧情。
你的任务：按下面 5 个维度各打 1-5 分（5 最好），并给出**具体、可执行**的修改意见。
不要泛泛而谈（不要说「可以更生动」），要指名道姓：哪个角色的哪个字段、哪一幕的哪条 directions/condition、
具体问题是什么、应该改成什么方向。

评分维度（rubric）：
1. character_depth 角色深度：每个 NPC 的 soul/inner 是否具体有棱角、非套话？inner 里的秘密/图谋是否
   与某个结局或某条剧情走向真正挂钩（而非悬空的通用设定）？
2. voice_distinct 声音可区分度：各 NPC 的 speech_style/speech_samples 是否在用词/句式/称谓/口头禅上彼此
   可分辨？有没有都写成同一个「通用 AI 腔」？对立阵营的角色尤其要能一眼听出是谁。
3. subtext_drama 潜台词与戏剧性：directions 是否给了潜台词（嘴上说 A 心里想 B）、是否 show-don't-tell？
   反派/有秘密的角色是否靠算计、伪装、试探推进，而不是直白敌意或一上来就摊牌？
4. player_agency 玩家纳入：有分支的节点，各出边 condition 是否互斥、清楚区分玩家的不同选择、且都是
   「玩家在对话里做到/表达了什么」可被判定的具体行动？玩家的选择是否真能导向不同走向/结局？
5. plot_tension 剧情张力：scene_brief 串起来是否有起承转合、悬念、转折？还是平铺直叙、每幕都在重复？

只输出 JSON：
{
  "scores": {"character_depth": 1-5, "voice_distinct": 1-5, "subtext_drama": 1-5, "player_agency": 1-5, "plot_tension": 1-5},
  "casting_feedback": "针对 Casting 的角色卡（soul/inner/speech_style/speech_samples/声音区分/反派算计）的具体修改清单；若该部分已经很好就留空字符串",
  "writer_feedback": "针对 Writer 的分幕（scene_brief/directions 潜台词/condition 互斥与玩家纳入/分支张力）的具体修改清单；若已经很好就留空字符串",
  "summary": "一句话总评"
}
feedback 要写成「① 角色X的inner太泛，应点明他对Y的具体图谋…；② 第二幕directions没有潜台词…」这种可直接照做的条目。"""


def _draft_payload(brief: Dict[str, Any], designer: Dict[str, Any],
                   casting: Dict[str, Any], writer: Dict[str, Any]) -> str:
    return (
        "故事 brief（作者意图）：\n" + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\n故事图骨架（节点/边/结局）：\n" + json.dumps(designer, ensure_ascii=False, indent=2)
        + "\n\n角色花名册（Casting）：\n" + json.dumps(casting.get("agents", []), ensure_ascii=False, indent=2)
        + "\n\n分幕血肉（Writer：每节点 scene_brief/directions、每边 condition）：\n"
        + json.dumps(writer, ensure_ascii=False, indent=2)
    )


class Critic:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def review(self, brief: Dict[str, Any], designer: Dict[str, Any],
               casting: Dict[str, Any], writer: Dict[str, Any]) -> Dict[str, Any]:
        user = _draft_payload(brief, designer, casting, writer)
        return call_json_with_schema(
            self._client, system=_SYSTEM, user=user, schema=CRITIC_OUTPUT_SCHEMA, label="critic"
        )
