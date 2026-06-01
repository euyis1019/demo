"""管理 agent（生成期）。单一 LLM 能力，client 注入，可离线单测。

剧情结构由 Bert 设计师（brief+cast→「条件→反应」规则集）承载；Casting 定世界原语。
旧的 Designer（任务链）/ Writer（分幕血肉）已随 story_graph 退役。
"""

from agent_world.drama_demo.tools.story_studio.agents.bert_designer import BertDesigner
from agent_world.drama_demo.tools.story_studio.agents.casting import Casting
from agent_world.drama_demo.tools.story_studio.agents.critic import Critic

__all__ = ["Casting", "BertDesigner", "Critic"]
