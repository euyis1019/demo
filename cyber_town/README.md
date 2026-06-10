# cyber_town —— 赛博小镇 demo（农场版活体世界）

基于 [agent_world/](../agent_world/) 引擎（只读底座）的星露谷式农场小镇。
完整方案见 [docs/赛博小镇-开发方案.md](../docs/赛博小镇-开发方案.md)。

## 目录结构（按层解耦）

```
cyber_town/
├── world_seed/            # 纯数据层：世界种子
│   ├── scenario.yaml      #   3 地点 / 4 agent / 关系 / 群 / 能力 / coverage
│   └── loader.py          #   灌库（照搬引擎 run_demo._seed_world，含 self-edge 补全）
├── backend/               # 后端薄应用层
│   ├── config.py          #   常量 + .env / LLM 配置解析（零依赖）
│   ├── actions.py         #   agent→引擎的动作数据形状（duck-type 契约）
│   ├── llm_client.py      #   LLM 工厂：真实 AsyncOpenAI / 离线 Mock 可互换
│   ├── npc.py             #   CyberTownNPC：LLM 村民（生活化提示词，允许沉默）
│   ├── player_agent.py    #   PlayerAgent：玩家虚拟农夫（不调 LLM，命令队列）
│   ├── scheduler.py       #   激活调度：同场每拍 + 异地低频心跳
│   ├── world_factory.py   #   内核装配（唯一成套 import agent_world 的地方）
│   ├── affinity/          #   M4：好感度薄层（独立 affinity.db；主路拦截+规则底噪）
│   ├── snapshot.py        #   M1：每拍世界快照（自管消息游标，勿用引擎 last_seen）
│   ├── ws_hub.py          #   M1：WS 连接管理 + 广播 + 玩家命令入队
│   ├── tick_loop.py       #   M1：固定墙钟心跳后台任务（变速拍 + 优雅退出）
│   ├── main.py            #   M1：FastAPI 入口（lifespan 装配 / /ws/world / /healthz）
│   ├── .env               #   LLM_API_KEY=...（gitignored，见 .env.example）
│   └── .env.example
├── frontend/              # M2：Godot 4.x 工程（全代码化生成，导入即跑）
│   ├── project.godot      #   像素渲染 + autoload（Config/WorldNet）
│   ├── scenes/            #   极简场景（根节点+脚本，子节点全由代码构建）
│   ├── scripts/           #   config/world_net/sprite_lib/player/npc/day_night/main
│   ├── assets/            #   CC0 图集与音频（来源见 CREDITS.md）
│   └── CREDITS.md         #   素材许可清单
├── tests/                 # pytest：调度/玩家命令/冒烟/快照游标/WS 端到端
├── requirements.txt       # 后端依赖（勿跑 pip install -e .）
└── run_m0.py              # M0 CLI：纯文本活体世界
```

## 运行

```bash
# 离线冒烟（Mock 剧本，零网络，全通道验收）
python3 -m cyber_town.run_m0 --mock-llm --num-ticks 8 --heartbeat 4

# 真实 LLM（DeepSeek 官方 deepseek-v4-flash；backend/.env 需 LLM_API_KEY）
python3 -m cyber_town.run_m0 --num-ticks 6 --heartbeat 4

# 测试
python3 -m pytest cyber_town/tests -q

# M1：后端 WS 服务（真实 LLM；Mock 加 CYBER_TOWN_MOCK=1）
uvicorn cyber_town.backend.main:app --port 8000
# 然后 WS 连 ws://127.0.0.1:8000/ws/world，REST 看 http://127.0.0.1:8000/healthz

# M2/M3：Godot 前端（先启动上面的后端）
# 用 Godot 4.x 打开 cyber_town/frontend/project.godot，按 F5 运行：
#   WASD/方向键 走动；走进「广场/酒馆」区域即自动前往（下一拍生效）
#   Tab 呼出「小镇通」菜单（当面说/私聊/群聊/记录，未读角标+提示音）
#   走近 NPC 按 E 直达与其的私聊会话
```

> ⚠ 用 Python `websockets` 库写调试客户端时务必 `connect(url, proxy=None)`——
> websockets 14+ 会读 macOS 系统代理，本机回环流量被代理截断会报
> "did not receive a valid HTTP response"（Godot 前端不受影响）。

## 阶段进度（方案 §12）

- [x] **M0** 活体世界纯文本跑通（Mock 全通道 + 真实 LLM 双验收 ✓；V1-V5 全过，单拍 avg 3.6s）
- [x] **M1** FastAPI 持续 tick + WS 推快照 + 玩家文本闭环（pytest ✓ + uvicorn 进程级验收 ✓）
- [x] **M2** Godot 渲染世界 + 键盘移动 + 氛围（headless 实跑验收 ✓ + 后端 e2e 连通 ✓）
- [x] **M3** 类手机菜单「小镇通」三渠道 + 按 E 直达（headless 消息流验收 ✓）
- [x] **M4** 好感度注入（27 pytest ✓ + 真实 LLM 验收：好感 30→34、语气生效、零泄漏 ✓）

> 视觉效果的最终确认需在 Godot 编辑器中打开运行（开发机无显示环境，
> 已用 headless 模式覆盖脚本解析/运行/WS 链路/消息流验收）。
