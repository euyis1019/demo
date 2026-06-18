"""NPC 的 7 个引擎工具 schema（原 agents/npc.py::TOOLS，W6 集中至 prompts）。

工具的中文 description 是 NPC 行为软引导的重要载体——改「怎么跟 LLM 介绍
这个动作」只改这里。

⚠ 工具名严格等于引擎 ActionType.value（agent_world/world/dispatcher.py），
一个字都不能改；好感度私有工具 adjust_affinity 在 prompts/affinity.py。
"""

from __future__ import annotations

from typing import Any, Dict, List

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "speak_to_local",
            "description": (
                "对当前地点里所有人当面说出口的话（同地点广播，在场的人都听见）。"
                "像真人当面唠嗑：**一次只说一句短话**（通常十来个字，最多一句），"
                "想说的多就分几拍、你一句我一句地来回——别一口气长篇大论。"
                "口语、不是『短信腔』，称呼随口、说事直接。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": (
                            "你这一拍说出口的一句短话（口语，越短越像真人；"
                            "一般 ≤20 字，别堆成一段。还有话下一拍接着说）。"
                        ),
                    }
                },
                "required": ["content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "给某个具体的人发私信（手机短信/微信，对方不在身边也能收到，"
                "异地约 1 拍后送达）。悄悄话、捎话、远程招呼用这个。"
                "**别人用私信找你，回他也用私信**（回到同一个『私聊』里他才看得见，"
                "哪怕他就站在你跟前——你当面喊一嗓子，他盯着私聊页是看不到的）；"
                "主动找身边的人聊才用当面说（speak_to_local）。"
                "像发微信：一条短消息说一件事，别写成长信。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "integer", "description": "收件人 agent_id"},
                    "content": {"type": "string",
                                "description": "一条短消息（口语，简短；多的话分几条发）"},
                },
                "required": ["target", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_to_group",
            "description": (
                "在你所在的群聊（镇民群）里发消息，全群成员下一拍都能看到。"
                "适合：跟全镇人说事、张罗活动、群里搭话起哄。"
                "**群里有人招呼/问话时，想接就用这个回到群里**——街坊群冷场没人应"
                "挺尴尬的；平时也可以主动在群里冒个泡、问句『谁在』。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["group_id", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_move",
            "description": (
                "走去另一个地点（本拍末出发，下一拍人在新地点）。"
                "按你的生活作息走动：串门、采买、收工去酒馆。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {"type": "string", "description": "目的地 place_id"},
                },
                "required": ["place_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_state",
            "description": (
                "更新自己的『当前状态』（你正在做什么/心里在想什么）。"
                "干活、歇着、心情变化都可以用它记录——不说话的拍子里，"
                "用它让别人看见你在过日子。**写具体的活计/姿态**（在锄地、在擦吧台、"
                "蹲田埂歇脚、躺树荫午歇、举杯乐呵…），街坊（和镜头）就能看见你此刻在忙啥。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_state": {
                        "type": "string",
                        "description": "新的状态描述，1-2 句。",
                    },
                },
                "required": ["new_state"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_short_term_goal",
            "description": (
                "更新自己的『当前小目标』（接下来一小段时间打算干嘛）。"
                "发现自己在原地打转/重复说同样的话时，先调它再行动。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_goal": {
                        "type": "string",
                        "description": "1-2 句，明确下一步。",
                    },
                },
                "required": ["new_goal"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "do_nothing",
            "description": (
                "这一拍安静过：发呆、继续手头的活、晒太阳。"
                "乡下日子慢，没事不必硬找话——这是完全正常的选择。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]
