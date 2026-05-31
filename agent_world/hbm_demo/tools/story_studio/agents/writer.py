"""Writer 管理 agent（dev_logs/45 §3.2）：给故事图补"血肉"。

单一能力：给节点绑 inject_agents/place_focus/window_since、给边补 trigger/actions/legacy_label、
产 signals（story_advance 白名单 + 关键词集合 + 参数）。引用必须闭合（inject_agents⊆角色、
trigger.signal⊆valid_signals…），否则 orchestrator 的 X 校验回路会回灌重生成。LLM 注入，离线可测。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import WRITER_OUTPUT_SCHEMA
from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是编剧。给故事图的节点与边补上运行所需细节。
只输出 JSON：
{
  "nodes": [{"id": "节点id", "inject_agents": [agent_id...], "place_focus": "地点id",
             "window_since": "start_tick"}],
  "edges": [{"id": "边id", "trigger": {触发条件}, "actions": [副作用...]}],
  "signals": {"story_advance": {"enabled": true, "valid_signals": []},
              "keyword_sets": {"集合名": ["词"...]}, "params": {}}
}

★最重要：触发必须「运行期可执行」。玩家靠**说话(台词)**推进剧情——玩家做某个选择 = 玩家说出含
特定关键词的一句话。所以**每条边的 trigger 用玩家台词关键词**：
  {"type":"f2f_keyword","place":"该边起点节点的地点","sender":0,"keyword_set":"集合名"}
  （sender:0 就是玩家本人；keyword_set 放玩家做这个选择时**可能说出的 3-6 个词/短语**）
并在 signals.keyword_sets 里定义每个 keyword_set。

✗ 不要用 {"type":"story_advance",...}！那种信号只有 NPC 调工具才发得出，玩家发不出，会导致
  剧情永远卡住推不动。把所有「玩家选择」一律写成 f2f_keyword(sender:0)。valid_signals 留空 []。

一个节点有多条出边时（分支），各边的 keyword_set 要用**不同**的关键词区分玩家的不同选择。

硬性约束：
- 每个非终结节点都要有 inject_agents（玩家在此节拍会对话的在场 NPC，至少 1 个已存在 agent_id）；
  place_focus 必须是已存在地点。
- 每条边都要有 f2f_keyword 触发(sender:0)，place 用该边起点节点的 place_focus，
  keyword_set 必须在 signals.keyword_sets 里定义。指向结局的边也照此。
- window_since 一律用 "start_tick"。"""


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
