"""玩家交互薄层：把结构化的「送心意/搭把手」命令翻译成引擎认得的动作。

红线：不新增引擎动词、不后端代加好感（NPC 自主领情）。详见 gift_help.py。
"""

from cyber_town.backend.interactions.gift_help import GiftHelp

__all__ = ["GiftHelp"]
