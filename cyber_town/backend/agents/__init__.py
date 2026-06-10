"""agents —— 世界里的 agent 实现（W6 拆分）。

* ``actions``       agent→引擎的动作返回形状（ToolCall/AgentResponse，引擎 duck-type 契约）
* ``npc``           CyberTownNPC：LLM 驱动村民（感知→决策→私有工具拦截）
* ``player_agent``  PlayerAgent：人类驱动虚拟农夫（不调 LLM，命令队列翻译）

提示词文本不在这里——见 cyber_town/backend/prompts/。
"""
