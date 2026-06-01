"""Writer 管理 agent（dev_logs/45 §3.2）：给故事图补"血肉"。

单一能力：给节点绑 inject_agents/place_focus、给每条边补一句自然语言 condition（导演据此判断
玩家是否推进到该边）。不再产关键词/信号/触发器——剧情推进交由 LLM 导演按对话理解。LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from agent_world.drama_demo.tools.story_studio.authoring_schemas import WRITER_OUTPUT_SCHEMA
from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是编剧。整个游戏是**任务式**的：每个 node 是一个**任务**，玩家被一个个任务推着走。
你的活：给每个任务绑上「发任务/检查任务的 NPC」与情境，给每条边写一句「任务算不算做成」的判定。
任务里的每个 NPC 会被 LLM「演员」实时扮演——**你给的任务情境与表演指引越具体，演员越贴剧情、不跑题**。
只输出 JSON：
{
  "nodes": [{"id": "任务id", "inject_agents": [agent_id...], "place_focus": "地点id",
             "scene_brief": "这个任务的情境：哪个 NPC 此刻要把什么任务交给玩家（或检查玩家有没有做成上一个任务）、为什么、玩家处境与张力在哪（2-3 句，画面感）",
             "directions": {"agent_id(字符串或整数)": "这个在场 NPC 在这个任务里的表演指引，写清三件："
                            "①他在这个任务里想让玩家做成什么/或要怎么验收上一个任务(意图)；②他怎么开口把任务交给玩家、或怎么旁敲侧击核实玩家是否办成(手段)；③他绝不能说出口的(藏着的)。"
                            "第二人称，2-3 句，紧扣他的人设与 inner，要有潜台词（嘴上一套心里一套）"}}],
  "edges": [{"id": "边id", "condition": "一句自然语言：玩家把这个任务做成（或以某种方式收官）才走这条边"}]
}

★任务由谁发、谁检查：每个任务的 inject_agents 是「这个任务里玩家要打交道的 NPC」——通常是**发布这个
任务的 NPC**；如果这个任务是承接上一个任务的检查/协助，就让对应的 NPC（往往和上一个任务不是同一人）在场。
让任务在不同 NPC 间接力（一个发、下一个验/帮），directions 把「怎么把任务交代清楚」「怎么确认玩家办没办成」
演出来。directions 的 key 用 inject_agents 里的 agent_id，每条写出【意图+手段+藏着的】三件，紧扣 casting 里的
soul/inner。要 show-don't-tell：用动作/神态/反问/回避表现情绪，而不是直接说"我很生气"。

★剧情推进交由 LLM「导演」按真实对话判断——**不要写任何关键词、信号、触发器、keyword_set 或 story_advance**。
每条边只写一句自然语言 condition，描述「玩家把这个任务做成了什么程度/做了什么，才算完成、走这条边」。

★condition 写成「玩家可被判定的具体行动/表态（= 任务达成）」，不要写成场景描述。
- 链中任务（只有 1 条出边）示例："玩家把密信亲手交到二师姐手里、并转述了师兄的口信"。
- 收官任务（多条出边分叉到不同结局）务必互斥、覆盖玩家不同的收官方式，例如同一个收官任务：
  - e_expose：玩家当众出示账册、指认二长老通敌（→ 好结局）
  - e_compromise：玩家私下与二长老和解、换取自保（→ 中性结局）
  - e_fail：玩家被反将一军、证据尽失（→ 坏结局）
  三条彼此不重叠、不会同时成立，导演能据玩家这一回合的话清楚判断走哪条、收哪个局。

硬性约束：
- 每个任务 node 都要有 inject_agents（这个任务里在场的 NPC，至少 1 个已存在 agent_id）+ place_focus（已存在地点）
  + scene_brief + 覆盖全部 inject_agents 的 directions。
- 每条边都要有一句非空、具体的 condition；指向结局的边也照此。
- 不要输出 signals / keyword_sets / trigger / window_since 等字段。"""


def _build_user_prompt(designer: Dict[str, Any], casting: Dict[str, Any],
                       brief: Optional[Dict[str, Any]] = None) -> str:
    parts = []
    if brief:
        parts.append("故事 brief（作者意图：题材/基调/结局走向，写 scene_brief 与 condition 时务必对齐）：\n"
                     + json.dumps(brief, ensure_ascii=False, indent=2))
    parts.append("故事图骨架：\n" + json.dumps(designer, ensure_ascii=False, indent=2))
    parts.append("世界原语（角色含 soul/inner/speech_style，地点）：\n" + json.dumps(
        {"agents": casting.get("agents"), "places": casting.get("places")},
        ensure_ascii=False, indent=2,
    ))
    return "\n\n".join(parts)


class Writer:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def run(self, designer: Dict[str, Any], casting: Dict[str, Any], *,
            brief: Optional[Dict[str, Any]] = None, feedback: str = "") -> Dict[str, Any]:
        user = _build_user_prompt(designer, casting, brief)
        if feedback:
            user += f"\n\n[上一版需修正，请按意见重新输出完整 JSON]\n{feedback}"
        return call_json_with_schema(
            self._client, system=_SYSTEM, user=user, schema=WRITER_OUTPUT_SCHEMA, label="writer"
        )
