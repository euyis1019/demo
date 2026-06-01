"""表演须知生成（管理 agent）：为整个故事的所有 actor agent 写一份「怎么演」的导演手册。

设计意图（dev_logs/43 管理 vs 演员）：运行期的 knowledge.py 只做**数据组装**，不写死任何表演规则；
所有「该怎么说话、什么时候开口、如何用潜台词演、如何接玩家、如何留在角色里」这类表演纪律，
统一由这个**管理 agent**按当前故事的基调**生成**，写进 Story Pack 的 meta.acting_guide，
运行期只注入、不内嵌规则。换 Story Pack 即换一套贴合新故事的表演须知。

单一职责，LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

ACTING_GUIDE_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["acting_guide"],
    "properties": {
        # 一段统一的表演须知（注入每个 actor 的知识块末尾）。贴合本故事基调，覆盖：
        # 口吻节奏 / show-don't-tell / 潜台词 / 如何接玩家 / 沉默纪律 / 留在角色。
        "acting_guide": {"type": "string", "minLength": 60},
    },
}

_SYSTEM = """你是这部互动剧情的**表演指导（导演）**。你的产物会作为统一的「表演须知」，
注入给本故事里**每一个** actor agent，指导他们每一拍该怎么演。请贴合这个具体故事的基调
（如悬疑→克制压抑、武侠→古意江湖气、轻喜→俏皮），写一份简短、可执行的须知。

须覆盖以下几点，用第二人称「你」对演员说话，凝练成几条，不要长篇大论：
1. 口吻与节奏：台词短、口语化、像面对面聊天（一般 1–4 句）；贴合各自的说话风格；禁论文腔/演讲腔。
2. show，别 tell：情绪与态度用神态、动作、语气、反问去表现，别直说「我很生气/我很害怕」。
3. 潜台词：心里藏着秘密或顾忌时，用旁敲侧击、回避、客套去演，不要直白说破。
4. 如何接玩家：玩家开口时，先接住他这一句的**具体内容与情绪**再据此回应，顺势带出你自己的目的；
   绝不无视玩家，也不要把话题硬拉回预设台词。
5. 沉默纪律（重要，别太活跃）：没有必要时不硬找话说、不刷存在感、不和别的 NPC 没事尬聊；这一拍你没有
   要紧的话或事、或只会重复别人，就 do_nothing，把舞台让给该说话的人或玩家。宁可少说、别群起刷屏。
6. 推进而非闲聊：每次开口都要**带着你这一幕的目的往前推**——追问、试探、施压、交代或验收任务、揭露、逼抉择，
   让剧情朝当前任务的目标走；绝不寒暄注水、不反复客套、不原地打转。你是在「演这场戏并推动它」，不是闲聊机器人。
7. 留在角色：你就是这个角色本人，只说/做此刻这个角色会说会做的；绝不跳出角色、不复述人设、
   不提及自己是 AI 或在演戏、不替玩家做决定、不替别的角色发言。

只输出 JSON：{"acting_guide": "贴合本故事基调的整段表演须知"}。
acting_guide 要能直接读给演员听，措辞贴这个故事（可点到本故事的情境/身份氛围），不要写成通用空话。"""


def _build_user(brief: Dict[str, Any], casting: Dict[str, Any]) -> str:
    agents = [
        {
            "name": a.get("name"),
            "role": a.get("role"),
            "speech_style": a.get("speech_style"),
        }
        for a in (casting.get("agents") or [])
        if int(a.get("agent_id", -1)) > 0
    ]
    # brief 本身已含 premise/tone（schema 只有这两项）；额外再点一句基调，帮 LLM 抓重点，不取 schema 里没有的幽灵字段。
    return (
        "故事 brief（前提 + 基调）：\n" + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\n登场角色与说话风格：\n" + json.dumps(agents, ensure_ascii=False, indent=2)
        + "\n\n基调 tone：" + str(brief.get("tone") or "（未指定，按 premise 自行判断）")
    )


def generate_acting_guide(
    brief: Dict[str, Any], casting: Dict[str, Any], client: LLMClient,
) -> str:
    """产出整段表演须知字符串。失败由 call_json_with_schema 抛错，调用方可吞掉不阻断生成。"""
    out = call_json_with_schema(
        client, system=_SYSTEM, user=_build_user(brief, casting),
        schema=ACTING_GUIDE_SCHEMA, label="acting_guide",
    )
    return str(out.get("acting_guide") or "").strip()
