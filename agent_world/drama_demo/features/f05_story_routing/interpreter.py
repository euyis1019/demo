"""StoryInterpreter：Story Pack 的薄封装，提供剧情图访问（节点 / 边 / 结局）。

剧情推进与结局判断已交由 LLM 导演（f05/director.py）按对话理解判断——本类**不再做任何
关键词 / RDC / 信号 / 超时等硬规则评估**，只缓存载入 Story Pack 并暴露其 graph 供导演与路由读取。
"""

from __future__ import annotations

from agent_world.drama_demo.shared.story_pack import StoryPack, load_story_pack
from agent_world.drama_demo.shared.story_pack.bert import BertSet
from agent_world.drama_demo.shared.story_pack.graph import StoryGraph


class StoryInterpreter:
    """以一份 Story Pack 驱动剧情决策（bert 规则集 + 图访问 + 缓存载入）。"""

    def __init__(self, pack: StoryPack) -> None:
        self.pack = pack
        self.graph: StoryGraph = pack.graph
        self.berts: BertSet = pack.berts  # 「条件→反应」规则集（新剧情驱动；旧任务包为空集）

    @classmethod
    def for_story(cls, story_id: str) -> "StoryInterpreter":
        return cls(load_story_pack(story_id))
