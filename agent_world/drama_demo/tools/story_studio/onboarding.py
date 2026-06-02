"""新手引导生成（管理 agent）：为玩家写一段开场引导——故事背景 + 此刻可做的行为。

由设计期管理 agent 产出，写进 Story Pack 的 meta.onboarding，运行期经 session 快照下发给前端弹窗。
单一职责，LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

ONBOARDING_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["title", "background", "tips"],
    "properties": {
        # 故事标题/一句话定位
        "title": {"type": "string"},
        # 从玩家第二人称视角的故事背景：你是谁、身处何境、眼下发生了什么、你的目标（篇幅按开局信息量自定）
        "background": {"type": "string", "minLength": 20},
        # 「你现在可以做什么」：结合本故事具体写 + 点出操作方式（条数自定，至少 1 条）
        "tips": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
}

_SYSTEM = """你是互动剧情的新手引导设计师。根据给你的故事 brief 与角色/开局信息，为「即将开始游玩的玩家」写一段开场引导。
玩家通过「直接打字说话」推进剧情，也能用动作条「移动到别处 / 私信某人 / 加入群聊」。剧情由 AI 导演按你的真实表达推进。
只输出 JSON：
{
  "title": "故事标题或一句话定位",
  "background": "用第二人称『你』写：你是谁、身处何境、眼下正发生什么、你要达成什么（篇幅按开局信息量自定，有代入感，避免剧透真凶/结局）",
  "tips": ["『你现在可以做什么』，条数自定（至少 1 条），结合本故事具体写、点出操作方式，例如：",
           "· 直接打字，对眼前的人说话、追问、表态来推进剧情",
           "· 想找别处或别人？用下方动作条『移动』去其它地点、『私信』单独联系某个角色"]
}
tips 要贴合这个具体故事（提到本故事的人/地点/悬念），不要写成通用空话；background 不要剧透关键真相。

**最关键**：若给了你「开局就能推进剧情的玩家动作」列表，tips 里**至少有一条**要把玩家明确指向其中一个可行的开局
动作——用故事语言重述成一个具体的「你不妨先…」的下一步（如"你不妨先向阿芸打听打听这茶馆楼上那间锁着的房"），
让玩家一进来就知道做什么能让剧情有反应。**绝不要**建议那些不在列表里、其实触发不了任何剧情的动作（那只会让玩家
照做却石沉大海）。不剧透后果，只指方向。"""


def _build_user(
    brief: Dict[str, Any], casting: Dict[str, Any], opening_triggers: Any = None,
) -> str:
    agents = [
        {"name": a.get("name"), "role": a.get("role"), "current_state": a.get("current_state")}
        for a in (casting.get("agents") or [])
        if int(a.get("agent_id", -1)) > 0
    ]
    places = [p.get("place_id") for p in (casting.get("places") or [])]
    parts = [
        "故事 brief：\n" + json.dumps(brief, ensure_ascii=False, indent=2),
        "\n\n登场角色（含开局处境）：" + json.dumps(agents, ensure_ascii=False),
        "\n地点：" + json.dumps(places, ensure_ascii=False),
        "\n玩家身份：" + json.dumps(brief.get("player") or {}, ensure_ascii=False),
    ]
    if opening_triggers:
        parts.append(
            "\n\n开局就能推进剧情的玩家动作（玩家做到其中任意一条，剧情就会有反应——"
            "tips 要把玩家往这些上引，但用故事语言重述、别照抄、别剧透后果）：\n"
            + json.dumps(list(opening_triggers), ensure_ascii=False, indent=2)
        )
    return "".join(parts)


def generate_onboarding(
    brief: Dict[str, Any], casting: Dict[str, Any], client: LLMClient,
    *, opening_triggers: Any = None,
) -> Dict[str, Any]:
    """产出 {title, background, tips}。失败由 call_json_with_schema 抛错，调用方可吞掉不阻断生成。

    opening_triggers：开局即可触发的玩家动作(trigger)列表，喂给引导让 tips 指向真能推进剧情的下一步，
    不再建议触发不了的死动作（"玩家不知道怎么推进"的主因之一）。
    """
    return call_json_with_schema(
        client, system=_SYSTEM, user=_build_user(brief, casting, opening_triggers),
        schema=ONBOARDING_SCHEMA, label="onboarding",
    )
