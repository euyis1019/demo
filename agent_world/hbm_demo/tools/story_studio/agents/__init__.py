"""管理 agent（生成期）。单一 LLM 能力，client 注入，可离线单测。

G2：Designer（brief→故事图骨架）。Casting/Writer/Producer/Artist 在 G3 接入。
"""

from agent_world.hbm_demo.tools.story_studio.agents.designer import Designer

__all__ = ["Designer"]
