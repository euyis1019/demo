"""prompts —— 全后端**所有软引导/提示词文本的唯一集中地**（W6）。

改任何「说给 LLM 听的话」只来这个目录；业务模块（agents/affinity/directors）
只保留取数与流程逻辑，文本一律从这里 import。

模块清单（按消费方分组）：

* ``segments``     引擎 5 段系统提示词标题（PerceptionBuilder 注入）
* ``npc_tools``    NPC 的 7 个引擎工具 schema（中文 description 即软引导）
* ``observation``  NPC user prompt 渲染（观察→生活化文本 + 【这一拍】纪律）
* ``affinity``     好感度：5 档指引文案 / adjust_affinity 工具 / 第 6 段文本
* ``directors``    两位导演：system prompt / user 模板 / 世界事件段渲染

⚠ 铁律级注意：
1. ``observation`` 里「# 当前 tick：t=」与「# 你是：agent_id=」两行格式被
   llm/client.py 的 Mock 正则反解依赖（_RE_AGENT/_RE_TICK）——措辞可调，
   这两个 ``t={t}`` / ``agent_id={id}`` token 不能动；
2. 自主性红线（方案 §4.8）：所有文本是「描述与纪律」不是「行为指令」——
   不许加行为模板/示例台词清单（W3 审计 B4 的回退禁区）。
"""
