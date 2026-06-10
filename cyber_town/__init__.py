"""赛博小镇 demo —— 基于 agent_world 引擎的农场乡村活体世界。

包结构（按层解耦）：

- ``world_seed/``  世界种子（scenario.yaml + loader，纯数据层）
- ``backend/``     后端薄应用层（配置 / LLM 客户端 / agent 适配 / 内核装配）
- ``run_m0``       M0 阶段 CLI：纯文本驱动活体世界跑 N 拍

铁律：agent_world 是只读底座，本包只做「数据 + 装配」，不改内核。
"""
