"""api —— 对前端的服务视图层（W6 拆分）。

* ``ws_hub``    WebSocket 集线器：连接/握手/广播/上行命令入队
* ``snapshot``  每拍世界快照构建（WS 下行 JSON，有状态、每世界一实例）
* ``timeline``  agent 行为时间线（REST /agents/{id}/timeline，档案页）

FastAPI 入口仍在 cyber_town/backend/main.py（uvicorn 路径不变）。
"""
