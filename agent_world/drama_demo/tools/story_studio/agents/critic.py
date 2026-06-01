"""Critic 管理 agent：结构合法后的「质量门」——按叙事 rubric 给整包草稿打分并给针对性修改意见。

研究依据（dev_logs 调研）：生成→按 rubric 批评→定向重写的小循环，质量显著优于一次成稿
（CritiqueLLM / ProTeGi 文本梯度）。本 agent 只评分 + 产可执行 feedback，是否需要重写由
orchestrator 按阈值决定，沿用现有 feedback 回灌通路重生成 Casting/Writer。单一职责，LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.drama_demo.tools.story_studio.authoring_schemas import CRITIC_OUTPUT_SCHEMA
from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是一位严格的叙事总监 + 角色扮演评审。下面是一个互动剧情「Story Pack 草稿」
（结构已合法）。这些角色会被 LLM「演员」实时扮演、由 LLM「导演」按玩家对话推进剧情。
你的任务：按下面 5 个维度各打 1-5 分（5 最好），并给出**具体、可执行**的修改意见。
不要泛泛而谈（不要说「可以更生动」），要指名道姓：哪个角色的哪个字段、哪条 bert 的 trigger/reaction、
具体问题是什么、应该改成什么方向。

评分维度（rubric）：
1. character_depth 角色深度：每个 NPC 的 soul/inner 是否具体有棱角、非套话？inner 里的秘密/图谋是否
   与某条 bert 反应或某个结局真正挂钩（而非悬空的通用设定）？
2. voice_distinct 声音可区分度：各 NPC 的 speech_style/speech_samples 是否在用词/句式/称谓/口头禅上彼此
   可分辨？有没有都写成同一个「通用 AI 腔」？对立阵营的角色尤其要能一眼听出是谁。
3. subtext_drama 潜台词与戏剧性：bert 的 reaction 是否有潜台词/层次（受压坦白、伪装动摇…），而不是直白？
   反派/有秘密的角色是否靠算计、伪装、试探推进，而不是直白敌意或一上来就摊牌？
4. player_agency 玩家纳入：各 bert 的 trigger 是否是「玩家在对话里做到/表达了什么」可被判定的具体行动、
   彼此不含糊、覆盖玩家可能的关键选择？玩家的不同做法是否真能导向不同反应/结局？
5. plot_tension 剧情张力：berts 经 requires/arms 串成的反应链是否有因果递进、悬念、转折（逼问→坦白→交代…）？
   还是各自孤立、平淡重复？结局是否够分量、与玩家历程相称？

只输出 JSON：
{
  "scores": {"character_depth": 1-5, "voice_distinct": 1-5, "subtext_drama": 1-5, "player_agency": 1-5, "plot_tension": 1-5},
  "casting_feedback": "针对 Casting 的角色卡（soul/inner/speech_style/speech_samples/声音区分/反派算计）的具体修改清单；若该部分已经很好就留空字符串",
  "bert_feedback": "针对 bert 反应链（trigger 是否玩家可做到且互不含糊、reaction 是否贴人设有潜台词、requires/arms 反应链是否连贯、结局是否够分量）的具体修改清单；若已经很好就留空字符串",
  "summary": "一句话总评"
}
feedback 要写成「① 角色X的inner太泛，应点明他对Y的具体图谋…；② bert『confess』的 trigger 太模糊，应写明玩家具体要做到什么…」这种可直接照做的条目。"""


def _draft_payload(brief: Dict[str, Any], casting: Dict[str, Any], bert_design: Dict[str, Any]) -> str:
    return (
        "故事 brief（作者意图）：\n" + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\n角色花名册（Casting）：\n" + json.dumps(casting.get("agents", []), ensure_ascii=False, indent=2)
        + "\n\nbert 反应链（条件→反应规则集，含结局 bert）：\n"
        + json.dumps(bert_design.get("berts", []), ensure_ascii=False, indent=2)
    )


class Critic:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def review(self, brief: Dict[str, Any], casting: Dict[str, Any],
               bert_design: Dict[str, Any]) -> Dict[str, Any]:
        user = _draft_payload(brief, casting, bert_design)
        return call_json_with_schema(
            self._client, system=_SYSTEM, user=user, schema=CRITIC_OUTPUT_SCHEMA, label="critic"
        )
