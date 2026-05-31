"""Writer 管理 agent（dev_logs/45 §3.2）：给故事图补"血肉"。

单一能力：给节点绑 inject_agents/place_focus、给每条边补一句自然语言 condition（导演据此判断
玩家是否推进到该边）。不再产关键词/信号/触发器——剧情推进交由 LLM 导演按对话理解。LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import WRITER_OUTPUT_SCHEMA
from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是编剧。给故事图的节点与边补上运行所需细节。
这一幕里的每个 NPC 会被 LLM「演员」实时扮演——**你给的每一幕情境与表演指引越具体，演员越贴剧情、不跑题**。
只输出 JSON：
{
  "nodes": [{"id": "节点id", "inject_agents": [agent_id...], "place_focus": "地点id",
             "scene_brief": "这一幕的戏剧情境：此刻正发生什么、张力/冲突在哪、玩家处在什么位置（2-3 句，画面感）",
             "directions": {"agent_id(字符串或整数)": "这个在场角色这一幕的表演指引，写清三件："
                            "①这一幕他想达成什么(意图)；②他怎么试探/帮助/阻挠玩家(手段)；③这一幕他绝不能说出口的(藏着的)。"
                            "第二人称，2-3 句，紧扣他的人设与 inner，要有潜台词（嘴上一套心里一套）"}}],
  "edges": [{"id": "边id", "condition": "一句自然语言"}]
}

★剧情推进交由 LLM「导演」按这一幕的真实对话来判断——**不要写任何关键词、信号、触发器、keyword_set
或 story_advance**。每条边只写一句自然语言 condition，描述「玩家在对话里做到/表达了什么，剧情才走这条边」。

★每个节点都要写 scene_brief（这一幕的情境）+ directions（**该节点 inject_agents 里每个角色**这一幕的表演指引）——
这是让演员"知道这一幕自己要干什么、怎么和玩家周旋"的关键，直接决定 NPC 演得贴不贴剧情。directions 的 key
用 inject_agents 里的 agent_id；每条指引都要写出【意图+手段+藏着的】三件，并紧扣该角色在 casting 里的 soul/inner
（比如卧底这一幕要怎么旁敲侧击套话、怎么用客气话遮掩慌张）。要 show-don't-tell：让角色用动作/神态/反问/回避
表现情绪，而不是直接说"我很生气"。

★condition 要写成「玩家可被判定的具体行动/表态」，不要写成场景描述。
单出边示例："玩家当众出示账册、指认二长老通敌"。
多出边（分支）务必互斥、覆盖玩家的不同选择，例如同一节点：
  - e_trust：玩家选择相信大师兄、把信物托付给他
  - e_doubt：玩家当面质疑大师兄、拒绝交出信物
  - e_stall：玩家既不表态也不交出、想拖延打探更多
三条彼此不重叠、不会同时成立，导演能据玩家这一回合的话清楚判断走哪条。

硬性约束：
- 每个非终结节点都要有 inject_agents（玩家在此节拍会对话的在场 NPC，至少 1 个已存在 agent_id）+ place_focus（已存在地点）
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
