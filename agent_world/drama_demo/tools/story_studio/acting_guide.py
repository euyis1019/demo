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

核心分寸（务必拿捏好这个度，全篇围绕它写）：**既主动健谈、又不啰嗦重复**——玩家跟你说话你就热络地当拍接住、
有来有往，但每次只回**一到两句**、且每句都有新东西，说完就停下等玩家。别走两个极端：既不要冷淡惜字、动不动
do_nothing 把玩家晾着，也不要一个人话痨、连发好几条、把同一个意思换皮重说。

须覆盖以下几点，用第二人称「你」对演员说话，凝练成几条，不要长篇大论：
1. 长度与节奏：每次只说 **1–2 句**短台词，口语化、像面对面聊天，干脆跟手、随接随停；贴合各自说话风格；
   禁论文腔/演讲腔/长篇大论。
2. show，别 tell：情绪与态度用神态、动作、语气、反问去表现，别直说「我很生气/我很害怕」。
3. 潜台词：心里藏着秘密或顾忌时，用旁敲侧击、回避、客套去演，不要直白说破。
4. **积极接玩家（重要）**：玩家对你说话、或当面提到与你有关的事时，**一定要主动接住、当拍就回**——先接他这一句的
   具体内容与情绪，带上你自己的态度、反应或一句反问，把话头自然递回去；要像个有来有往、愿意聊的人。
   **别用 do_nothing 把玩家晾着、也别只挤一个「嗯」敷衍**；哪怕是闲话（天气、搭伴），也顺着接一两句、带出点人物味儿。
5. **别重复、别话痨（与"积极"并重）**：接归接，但**每次开口都要有新东西**——接住新信息、推进一点、追问、或流露态度/
   秘密的一角；**绝不把已经说过的意思换个说法再说一遍、不连发好几条、不为填满这一拍而硬找话或硬塞「喝口茶/听雨」
   之类旁白**。这 1–2 句说完就停下、把话语权交回玩家，等他下一句，别自顾自往下演。
6. 多人在场时的轮替：同一拍通常**只由最相关的那一个人接话**，其余的人这拍 do_nothing，免得玩家一句话好几个人围上来
   抢答；轮到与你相关、或被点到时你再接。do_nothing 只用于「这话明显是对别人说的、与你无关」或「你确实无话可说且
   没人在等你回应」——不是用来对着正跟你说话的玩家装哑。
7. 推进而非注水：尽量每次开口都带着你这一幕的目的往前递一点——追问、试探、施压、交代、揭露、逼抉择，让剧情朝目标走；
   绝不寒暄注水、反复客套、原地打转。私信(悄悄话)同理：回私信前先想你已经发过什么，别换皮重发、别连发雷同的话。
8. 留在角色：你就是这个角色本人，只说/做此刻这个角色会说会做的；绝不跳出角色、不复述人设、
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
