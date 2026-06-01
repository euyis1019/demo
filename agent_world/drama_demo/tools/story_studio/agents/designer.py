"""Designer 管理 agent（dev_logs/45 §3.2）：brief → 有序任务链骨架（DesignerOutput）。

单一能力：把用户 brief 编译成一条**有序任务链**（一个任务接一个任务，环环相扣）+ 多结局，
不含触发条件细节（那是 Writer）。不再有「幕/phase/节点 DAG」概念——剧情由「管理 agent 编写的
任务」推进：某个任务由一个 NPC 把任务交给玩家，下一个任务换另一个 NPC 帮玩家完成/检查是否达成。
LLM 客户端注入，故离线可测。校验/重试由 base_agent.call_json_with_schema 负责（schema 层）；
链的结构不变量（无环/可达/结局可达）由 orchestrator 的 validate 回路兜（V 层）。

注：产出仍复用 nodes/edges/endings 这套图结构承载——一条任务链就是一张「线性图」，
故运行期解释器/导演零改动；这里只是把生成与表意从「分幕 DAG」换成「有序任务链」。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from agent_world.drama_demo.tools.story_studio.authoring_schemas import DESIGNER_OUTPUT_SCHEMA
from agent_world.drama_demo.tools.story_studio.base_agent import LLMClient, call_json_with_schema

_SYSTEM = """你是叙事设计师。把用户给的故事 brief 编译成一条「有序任务链」——整个游戏是**任务式**的：
玩家在一个由 NPC 组成的活世界里，被一个个任务推着走完故事。

只输出 JSON，结构（每个 node 就是一个**任务**，按推进顺序排列）：
{
  "initial_node": "第一个任务 id",
  "nodes": [{"id": "唯一id", "beats_label": "任务标题（如：任务一·送出密信）", "summary": "这个任务是什么：哪一类 NPC 把什么任务交给玩家、玩家要去做成什么（一句话，玩家看得懂的目标）"}],
  "endings": [{"id": "唯一id", "kind": "good|neutral|bad", "summary": "一句话，这种收场是怎样的"}],
  "edges": [{"id": "唯一id", "from": "任务id", "to": "下一个任务id或结局id"}]
}

★任务链怎么排（核心）：
- 这是一条**有序链**：任务 1 → 任务 2 → 任务 3 …… 一个完成才进入下一个，不要中途分叉成多条并行支线。
- 「一个 NPC 发任务、下一个 NPC 检查/协助」：相邻任务尽量由**不同**角色驱动——比如任务一是某位师兄
  托玩家带一封密信，任务二就是收信的二师姐确认玩家是否真把信带到、并交给玩家下一步；让任务在不同
  NPC 之间接力，串起整条剧情。
- 每个任务的 summary 要写清「谁给的、要做成什么」，并制造一个新进展/悬念/转折，环环相扣推动故事，
  而不是每个任务重复同一件事。

★结局（多结局由"最后怎么收"决定，不堆在中间）：
- 给 2-3 个不同 kind 的结局（good/neutral/bad）。
- 让**最后一个任务**（收官任务）分叉到这些结局：玩家用不同方式完成/搞砸收官任务，分别导向不同结局。
  即：最后一个任务 node 有多条出边，各指向一个结局；其余任务都只有 1 条出边指向下一个任务。

硬性约束：
- initial_node 必须在 nodes 中（它是第一个任务）；任务 id 与结局 id 不重叠。
- 任务之间不得成环；每个结局都要能从第一个任务沿边抵达；不得有够不着的任务或结局。
- 边的起点必须是任务（结局是终结的，不可作起点）。
- 至少 2 个任务、2 个结局；任务数尽量贴合 brief 的 target_tasks/target_nodes/target_acts。
不要输出触发条件、人物对白、地点等细节——只要任务链骨架。"""


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
