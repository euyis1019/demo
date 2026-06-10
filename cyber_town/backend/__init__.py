"""赛博小镇后端薄应用层。

模块职责（解耦边界）：

- ``config``        常量 + .env / LLM 配置解析（不 import 引擎）
- ``actions``       agent 返回给引擎的动作数据形状（不 import 引擎）
- ``llm_client``    LLM 客户端工厂：真实 AsyncOpenAI / 离线 Mock 可互换
- ``npc``           CyberTownNPC：LLM 驱动村民（生活化提示词，允许沉默）
- ``player_agent``  PlayerAgent：人类驱动虚拟农夫（不调 LLM，命令队列）
- ``scheduler``     ActivationScheduler：同场每拍 + 异地低频心跳
- ``world_factory`` 内核装配（唯一 import agent_world 全家桶的地方）
"""
