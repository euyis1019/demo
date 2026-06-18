# cyber_town —— 赛博小镇 demo（农场版活体世界）

基于 [agent_world/](../agent_world/) 引擎（只读底座）的星露谷式农场小镇。
完整方案见 [docs/赛博小镇-开发方案.md](../docs/赛博小镇-开发方案.md)。

## 目录结构（按层解耦）

```
cyber_town/
├── world_seed/            # 纯数据层：世界种子
│   ├── scenario.yaml      #   3 地点 / 4 agent / 关系 / 群 / 能力 / coverage
│   └── loader.py          #   灌库（照搬引擎 run_demo._seed_world，含 self-edge 补全）
├── backend/               # 后端（W6 按功能分包；详见 backend/__init__.py 包地图）
│   ├── main.py            #   FastAPI 入口（uvicorn 路径不变）
│   ├── config.py          #   常量 + .env / LLM 配置解析（零依赖）
│   ├── prompts/           #   ★ 所有软引导/提示词文本的唯一集中地
│   ├── agents/            #   actions / npc / player_agent
│   ├── runtime/           #   world_factory / scheduler / tick_loop
│   ├── api/               #   ws_hub / snapshot / timeline
│   ├── llm/               #   client（真实/Mock 工厂）/ json_call（JSON 元决策）
│   ├── affinity/          #   M4：好感度薄层（独立 affinity.db；100% LLM 主路）
│   ├── directors/         #   W5：管理类 agent（激活导演 / 世界事件导演）
│   ├── .env               #   LLM_API_KEY=...（gitignored，见 .env.example）
│   └── .env.example
├── frontend_web/          # 前端：Three.js + React-Three-Fiber 真 3D（唯一前端）
│   ├── src/net/           #   ws.ts（WS 客户端）/ protocol.ts（协议类型）
│   ├── src/store/         #   worldStore / chatStore（zustand）
│   ├── src/scene/         #   Scene/Ground/Props/Agent/Player/Character/Model/CameraRig
│   ├── src/ui/            #   Hud / PhoneMenu（小镇通聊天，React DOM）
│   ├── public/models/     #   KayKit 角色 GLB + Quaternius 村庄/自然/作物 GLB（CC0）
│   └── package.json       #   vite + react + three + r3f + drei + zustand
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

# 后端测试
python3 -m pytest cyber_town/tests -q

# 🌐 Web 端（真 3D，推荐）：先出包，再起后端同源托管
cd cyber_town/frontend_web && npm install && npm run build && cd -
uvicorn cyber_town.backend.main:app --port 8000   # Mock 加 CYBER_TOWN_MOCK=1
# 浏览器打开 http://127.0.0.1:8000/game/
#   操作：WASD/方向键 走动；走进区域即自动前往；Tab 呼出「小镇通」
#   （当面说/私聊/群聊/档案）；走近村民按 E 直达私聊；点击村民看档案
# 前端开发热重载：cd cyber_town/frontend_web && npm run dev → http://localhost:5173/game/
```

详细启动/出包/常见问题见 [docs/启动指南.md](../docs/启动指南.md)。

> ⚠ 用 Python `websockets` 库写调试客户端时务必 `connect(url, proxy=None)`——
> websockets 14+ 会读 macOS 系统代理，本机回环流量被代理截断会报
> "did not receive a valid HTTP response"（Godot 前端不受影响）。

## 阶段进度（方案 §12）

- [x] **M0** 活体世界纯文本跑通（Mock 全通道 + 真实 LLM 双验收 ✓；V1-V5 全过，单拍 avg 3.6s）
- [x] **M1** FastAPI 持续 tick + WS 推快照 + 玩家文本闭环（pytest ✓ + uvicorn 进程级验收 ✓）
- [x] **M2** Godot 渲染世界 + 键盘移动 + 氛围（headless 实跑验收 ✓ + 后端 e2e 连通 ✓）
- [x] **M3** 类手机菜单「小镇通」三渠道 + 按 E 直达（headless 消息流验收 ✓）
- [x] **M4** 好感度注入（真实 LLM 验收：好感 30→34、语气生效、零泄漏 ✓）
- [x] **M5** 场景装饰（CC0 图集，截图验收 ✓）
- [x] **M6** 村民档案页（点击 NPC 看行为时间线：对话双向/内心OS/移动，31 pytest ✓）
- [x] **W1** 视觉全面重构（Ninja Adventure CC0：双层 tilemap 整图 + 四角色差异化 + 和风 BGM）
- [x] **W2** Web 端化（Godot Web 导出 + FastAPI `/game` 托管 + WS 同源自适应 +
  中文像素字体内嵌；Chrome 无头端到端验收：画面 ✓ WS ✓ 中文 ✓）

> 视觉效果的最终确认需在 Godot 编辑器中打开运行（开发机无显示环境，
> 已用 headless 模式覆盖脚本解析/运行/WS 链路/消息流验收）。
