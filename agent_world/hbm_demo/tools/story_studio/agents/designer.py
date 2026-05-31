"""Designer 管理 agent（dev_logs/45 §3.2）：brief → 故事图骨架（DesignerOutput）。

单一能力：把用户 brief 编译成 DAG 骨架（节点/边/结局），不含触发条件细节（那是 Writer）。
LLM 客户端注入，故离线可测。校验/重试由 base_agent.call_json_with_schema 负责（schema 层）；
更深的 DAG 不变量（无环/可达）由 orchestrator 的 validate 回路兜（V 层）。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import DESIGNER_OUTPUT_SCHEMA
from agent_world.hbm_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是叙事设计师。把用户给的故事 brief 编译成一张「故事图骨架」(DAG)。
只输出 JSON，结构：
{
  "initial_node": "起始节点 id",
  "nodes": [{"id": "唯一id", "beats_label": "幕标签", "summary": "一句话"}],
  "endings": [{"id": "唯一id", "kind": "good|neutral|bad", "summary": "一句话"}],
  "edges": [{"id": "唯一id", "from": "节点id", "to": "节点或结局id"}]
}
硬性约束：
- initial_node 必须在 nodes 中；节点与结局 id 不重叠。
- 节点之间不得成环；每个结局都要能从 initial_node 沿边抵达；不得有孤儿节点。
- 边的起点必须是节点（结局不可作起点，结局是终结的）。
- 至少 1 个节点、1 个结局、1 条边。幕数尽量贴合 brief 的 target_acts/target_nodes。
不要输出触发条件、人物对白、地点等细节——只要骨架。"""


def _build_user_prompt(brief: Dict[str, Any]) -> str:
    return "故事 brief（YAML/JSON）：\n" + json.dumps(brief, ensure_ascii=False, indent=2)


class Designer:
    """brief → DesignerOutput。"""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def run(self, brief: Dict[str, Any], *, feedback: str = "") -> Dict[str, Any]:
        user = _build_user_prompt(brief)
        if feedback:
            user += f"\n\n[上一版校验未过，请修正后重新输出完整 JSON]\n{feedback}"
        return call_json_with_schema(
            self._client,
            system=_SYSTEM,
            user=user,
            schema=DESIGNER_OUTPUT_SCHEMA,
            label="designer",
        )
