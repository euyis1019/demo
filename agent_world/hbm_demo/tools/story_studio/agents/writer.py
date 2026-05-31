"""Writer 管理 agent（dev_logs/45 §3.2）：给故事图补"血肉"。

单一能力：给节点绑 inject_agents/place_focus、给每条边补一句自然语言 condition（导演据此判断
玩家是否推进到该边）。不再产关键词/信号/触发器——剧情推进交由 LLM 导演按对话理解。LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import WRITER_OUTPUT_SCHEMA
from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是编剧。给故事图的节点与边补上运行所需细节。
只输出 JSON：
{
  "nodes": [{"id": "节点id", "inject_agents": [agent_id...], "place_focus": "地点id"}],
  "edges": [{"id": "边id", "condition": "一句自然语言"}]
}

★最重要：剧情推进交由 LLM「导演」按这一幕的真实对话来判断——**不要写任何关键词、信号、触发器、
keyword_set 或 story_advance**。每条边只写一句自然语言 condition，描述「玩家在对话里做到/表达了
什么，剧情才走这条边」。导演会读这一幕玩家与 NPC 的真实对话，判断玩家是否已明确做到某条 condition。

condition 示例：
  "玩家决定跟踪那个可疑的长老，去查他深夜的去向"
  "玩家选择相信二师姐、与她联手对付幕后黑手"
  "玩家当众出示证据、指认真正的内奸"

一个节点有多条出边时（分支），各边的 condition 要清楚区分玩家的不同选择，彼此不重叠、不含糊。

硬性约束：
- 每个非终结节点都要有 inject_agents（玩家在此节拍会对话的在场 NPC，至少 1 个已存在 agent_id）；
  place_focus 必须是已存在地点。
- 每条边都要有一句非空、具体的 condition；指向结局的边也照此（描述触发该结局的玩家选择）。
- 不要输出 signals / keyword_sets / trigger / window_since 等字段。"""


def _build_user_prompt(designer: Dict[str, Any], casting: Dict[str, Any]) -> str:
    return (
        "故事图骨架：\n" + json.dumps(designer, ensure_ascii=False, indent=2)
        + "\n\n世界原语（角色/地点）：\n" + json.dumps(
            {"agents": casting.get("agents"), "places": casting.get("places")},
            ensure_ascii=False, indent=2,
        )
    )


class Writer:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def run(self, designer: Dict[str, Any], casting: Dict[str, Any], *, feedback: str = "") -> Dict[str, Any]:
        user = _build_user_prompt(designer, casting)
        if feedback:
            user += f"\n\n[上一版校验未过，请修正后重新输出完整 JSON]\n{feedback}"
        return call_json_with_schema(
            self._client, system=_SYSTEM, user=user, schema=WRITER_OUTPUT_SCHEMA, label="writer"
        )
