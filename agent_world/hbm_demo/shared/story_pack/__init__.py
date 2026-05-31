"""Story Pack 数据层（dev_logs/42 §3 / dev_logs/45）。

纯数据模型 + 图算法 + validate 闸门 + 加载器，**无业务规则、不依赖 features**（D3）。
故事解释（信号→转移）在 L2 features/f05_story_routing；运行期播种在 L1。

公共出口：
  - StoryGraph / StoryNode / StoryEnding / StoryEdge —— 故事图数据结构
  - load_story_graph / load_and_validate_story_graph / load_meta —— 加载器
  - StoryPackError / StoryPackValidationError —— 错误类型
"""

from __future__ import annotations

from agent_world.hbm_demo.shared.story_pack.errors import (
    StoryPackError,
    StoryPackValidationError,
)
from agent_world.hbm_demo.shared.story_pack.graph import StoryGraph
from agent_world.hbm_demo.shared.story_pack.loader import (
    list_story_ids,
    load_and_validate_story_graph,
    load_meta,
    load_story_graph,
)
from agent_world.hbm_demo.shared.story_pack.model import (
    StoryEdge,
    StoryEnding,
    StoryNode,
)
from agent_world.hbm_demo.shared.story_pack.pack import (
    StoryPack,
    load_and_validate_story_pack,
    load_story_pack,
)
from agent_world.hbm_demo.shared.story_pack.scenario_adapter import (
    is_story_pack_seed_enabled,
    load_scenario_from_story_pack,
    story_pack_to_scenario,
)

__all__ = [
    "StoryGraph",
    "StoryNode",
    "StoryEnding",
    "StoryEdge",
    "StoryPack",
    "list_story_ids",
    "load_story_graph",
    "load_and_validate_story_graph",
    "load_story_pack",
    "load_and_validate_story_pack",
    "story_pack_to_scenario",
    "load_scenario_from_story_pack",
    "is_story_pack_seed_enabled",
    "load_meta",
    "StoryPackError",
    "StoryPackValidationError",
]
