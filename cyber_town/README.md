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
│   ├── .env               #   LLM_API_KEY=...（gitignored，见 .env.example）
│   └── .env.example
├── tests/                 # pytest：调度不变量 / 玩家命令 / 全链路冒烟
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
```

## 阶段进度（方案 §12）

- [x] **M0** 活体世界纯文本跑通（Mock 全通道 + 真实 LLM 双验收 ✓；V1-V5 全过，单拍 avg 3.6s）
- [ ] M1 FastAPI 持续 tick + WS 推快照 + 玩家文本闭环
- [ ] M2 Godot 渲染世界 + 键盘移动 + 氛围
- [ ] M3 类手机菜单三渠道闭环 + 按 E 直达
- [ ] M4 好感度注入
