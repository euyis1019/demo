"""cyber_town.backend —— 赛博小镇后端（W6 重组后的包地图）。

根级（位置不动：uvicorn 入口与 .env 红线路径依赖）：
* ``main``       FastAPI 入口（uvicorn cyber_town.backend.main:app）
* ``config``     零依赖配置：跨层常量 / .env 加载 / LLMConfig 解析

功能包：
* ``prompts``    ★ 所有软引导/提示词文本的唯一集中地（改文案只来这里）
* ``agents``     agent 实现：actions / npc / player_agent
* ``runtime``    世界运行：world_factory / scheduler / tick_loop
* ``api``        前端服务视图：ws_hub / snapshot / timeline
* ``llm``        LLM 接入：client（真实/Mock 工厂）/ json_call（JSON 元决策调用）
* ``affinity``   好感度薄层：store（SQLite）/ manager（业务门面）
* ``directors``  管理类 agent：activation_director / world_director（§15）
"""
