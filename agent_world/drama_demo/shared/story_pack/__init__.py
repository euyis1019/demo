"""Story Pack 数据层（dev_logs/48）。

纯数据模型 + validate 闸门 + 加载器，**无业务规则、不依赖 features**（D3）。
剧情结构是 bert（条件→反应链，`bert.py`）；story_graph 已退役，`StoryGraph` 仅剩兼容空壳。
运行期播种在 L1，剧情路由在 L2 features/f05_story_routing。

公共出口：
  - Bert / BertSet —— bert（条件→反应）剧情结构
  - StoryPack / load_story_pack / load_and_validate_story_pack —— 整包
  - StoryGraph —— 已退役空壳（loader/pack 降级用）
  - StoryPackError / StoryPackValidationError —— 错误类型
"""

from __future__ import annotations

from agent_world.drama_demo.shared.story_pack.bert import Bert, BertSet
from agent_world.drama_demo.shared.story_pack.errors import (
    StoryPackError,
    StoryPackValidationError,
)
from agent_world.drama_demo.shared.story_pack.graph import StoryGraph
from agent_world.drama_demo.shared.story_pack.loader import (
    list_story_ids,
    load_meta,
    load_story_graph,
)
from agent_world.drama_demo.shared.story_pack.pack import (
    StoryPack,
    load_and_validate_story_pack,
    load_story_pack,
)
from agent_world.drama_demo.shared.story_pack.scenario_adapter import (
    is_story_pack_seed_enabled,
    story_pack_to_scenario,
)

__all__ = [
    "StoryGraph",
    "Bert",
    "BertSet",
    "StoryPack",
    "list_story_ids",
    "load_story_graph",
    "load_story_pack",
    "load_and_validate_story_pack",
    "story_pack_to_scenario",
    "is_story_pack_seed_enabled",
    "load_meta",
    "StoryPackError",
    "StoryPackValidationError",
]
