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
             "window_since": "start_tick|phaseN_start_tick"}],
  "edges": [{"id": "边id", "legacy_label": "可选",
             "trigger": {触发条件}, "actions": [副作用...]}],
  "signals": {"story_advance": {"enabled": true, "valid_signals": ["信号名"...]},
              "keyword_sets": {"集合名": ["词"...]}, "params": {"参数名": 值}}
}
trigger 叶子类型可用：
  {"type":"story_advance","signal":"信号名"}   // signal 必须在 signals.valid_signals 里
  {"type":"rdc_keyword","sender":id,"recipient":id,"keyword_set":"集合名"}
  {"type":"f2f_keyword","place":"地点id","sender":id,"keyword_set":"集合名"}
  可用 {"any_of":[...]} / {"all_of":[...]} 组合。
硬性约束：
- 每个非终结节点都要有 inject_agents（玩家这句话注入给谁），且都是已存在的 agent_id；
  place_focus 必须是已存在地点。
- 每条边都要有 trigger；trigger 里引用的 signal 必须在 signals.valid_signals，keyword_set 必须在
  signals.keyword_sets。指向结局的边也要有 trigger。"""


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
