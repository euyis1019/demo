"""runtime —— 世界运行层（W6 拆分）。

* ``world_factory``  内核装配：scenario dict → AssembledWorld（唯一成套 import agent_world 的模块）
* ``scheduler``      激活调度：每拍谁获得思考机会（可接激活导演档位）
* ``tick_loop``      心跳协程：run_one_tick → 导演钩子 → 快照 → WS 广播
"""
