"""新手引导生成（管理 agent）：为玩家写一段开场引导——故事背景 + 此刻可做的行为。

由设计期管理 agent 产出，写进 Story Pack 的 meta.onboarding，运行期经 session 快照下发给前端弹窗。
单一职责，LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

ONBOARDING_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["title", "background", "tips"],
    "properties": {
        # 故事标题/一句话定位
        "title": {"type": "string"},
        # 从玩家第二人称视角的故事背景：你是谁、身处何境、眼下发生了什么、你的目标（2-4 句）
        "background": {"type": "string", "minLength": 20},
        # 「你现在可以做什么」：3-5 条，结合本故事具体写 + 点出操作方式
        "tips": {"type": "array", "items": {"type": "string"}, "minItems": 2},
    },
}

_SYSTEM = """你是互动剧情的新手引导设计师。根据给你的故事 brief 与角色/开局信息，为「即将开始游玩的玩家」写一段开场引导。
玩家通过「直接打字说话」推进剧情，也能用动作条「移动到别处 / 私信某人 / 加入群聊」。剧情由 AI 导演按你的真实表达推进。
只输出 JSON：
{
  "title": "故事标题或一句话定位",
  "background": "用第二人称『你』写 2-4 句：你是谁、身处何境、眼下正发生什么、你要达成什么（代入感，避免剧透真凶/结局）",
  "tips": ["3-5 条『你现在可以做什么』，结合本故事具体写，并点出操作方式，例如：",
           "· 直接打字，对眼前的人说话、追问、表态来推进剧情",
           "· 想找别处或别人？用下方动作条『移动』去其它地点、『私信』单独联系某个角色"]
}
tips 要贴合这个具体故事（提到本故事的人/地点/悬念），不要写成通用空话；background 不要剧透关键真相。"""


def _build_user(brief: Dict[str, Any], designer: Dict[str, Any], casting: Dict[str, Any]) -> str:
    agents = [
        {"name": a.get("name"), "role": a.get("role")}
        for a in (casting.get("agents") or [])
        if int(a.get("agent_id", -1)) > 0
    ]
    places = [p.get("place_id") for p in (casting.get("places") or [])]
    return (
        "故事 brief：\n" + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\n开局节点（第一幕）：\n" + json.dumps(
            (designer.get("nodes") or [{}])[0], ensure_ascii=False)
        + "\n\n登场角色：" + json.dumps(agents, ensure_ascii=False)
        + "\n地点：" + json.dumps(places, ensure_ascii=False)
        + "\n玩家身份：" + json.dumps(brief.get("player") or {}, ensure_ascii=False)
    )


def generate_onboarding(
    brief: Dict[str, Any], designer: Dict[str, Any], casting: Dict[str, Any], client: LLMClient,
) -> Dict[str, Any]:
    """产出 {title, background, tips}。失败由 call_json_with_schema 抛错，调用方可吞掉不阻断生成。"""
    return call_json_with_schema(
        client, system=_SYSTEM, user=_build_user(brief, designer, casting),
        schema=ONBOARDING_SCHEMA, label="onboarding",
    )
