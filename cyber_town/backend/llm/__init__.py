"""llm —— LLM 接入层（W6 拆分）。

* ``client``     make_llm_client：真实 AsyncOpenAI / 离线 MockLLMClient 工厂
* ``json_call``  call_llm_json：JSON 输出的轻量调用（导演等元决策用，fail-soft）
"""
