# 数据驱动多 agent 互动剧引擎
一个**本地可玩的叙事谈判 Demo**：玩家扮演创业者，在 NVIDIA 接待 / 谈判场景中通过约
25 轮台词推动剧情，目标是走向三种结局之一（加入 NVIDIA / 拿种子轮独立 / 冷场破局）。

底层是一个**通用 LLM 多 Agent 世界仿真引擎**（`agent_world/`），本 Demo 是它的一个
scenario。运行时由三部分组成：

- **Runner** — `python -m agent_world.drama_demo.run_drama`：跑 LLM 多 Agent 世界仿真，
  写 `sim/<story_id>/world.db`（默认 `canglan_sword`），按 tick 推进。
- **Flask**（`agent_world.app` + `drama_bp`）：会话、玩家回合 API、只读 DB、增量同步。
- **React + Vite 前端**（`web/`，默认 `:5173`）：双栏世界舞台 + 可选沉浸式剧情模式。

```text
浏览器(Vite:5173) → Flask(drama_bp) → features/* handler → IPC → Runner(run_drama)
                                                              → sim/<story_id>/world.db
玩家每发一句 → 打分(F04) → inject 到 Runner(F11/F07) → 世界 tick → 前端靠 F14
/world-delta 轮询(+F16 WS)合并增量,回放各 Agent 动作。
```

---

## 快速开始

在**仓库根目录**执行：

```bash
# 1. Python 依赖（首次）
pip install -e .

# 2. API Key（DeepSeek，经 DMXAPI_KEY）
cp agent_world/drama_demo/.env.example agent_world/drama_demo/.env
# 编辑 .env：DMXAPI_KEY=sk-...

# 3. 一行启动 Runner + Flask + Vite
./agent_world/drama_demo/scripts/ops/start_demo.sh
```

浏览器打开 **http://localhost:5173**。`Ctrl+C` 或 `./agent_world/drama_demo/scripts/ops/stop_demo.sh` 停止。

**验收门禁**（自动起停 Runner/Flask，跑 E2E + 前端构建）：

```bash
python3 agent_world/drama_demo/scripts/test_m0_acceptance.py
cd agent_world/drama_demo/web && npm run build
```


---

## 四层架构

```text
L0 配置     config/prompts/*, config/stories/<id>/, .env        ← 场景/Prompt/路由/Key
L1 Runner   core/runner/  (+ integration/ 白名单桥)          ← 写 world.db、tick、Agent LLM、IPC
L2 编排     features/f01–f17                                  ← 回合规则、路由、打分、世界同步
L3 传输/UI  http/ (REST + WS), web/src/                       ← Flask Blueprint + React 双栏 UI
shared/     config_loader / env_status / errors / settings / messages / prompt_paths / routing_events
```

依赖硬规则与运行时数据流详见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

---

## 目录结构

```text
agent_world/drama_demo/
├── README.md                 # 本文件（总览）
├── ARCHITECTURE.md           # 四层架构 + 依赖规则 + 运行时数据流
├── run_drama.py                # 入口 shim → core/runner/run_drama.py
├── routes.py                 # 入口 shim → http/routes.drama_bp
├── game_service.py           # 历史 re-export facade（F01–F04/F06，逐步退役）
├── config/stories/<id>/         # L0 场景：地点 / Agent soul / LLM / 群聊
├── .env / .env.example       # L0 API Key（.env 不入库）
│
├── config/                   # L0 配置（见 config/prompts/README.md）
│   ├── manifest.yaml         #   prompt 路径索引
│   └── prompts/              #   Agent prompt / 路由 / 虚拟玩家 YAML
├── core/runner/              # L1 Runner（见 core/runner/README.md）
├── features/                 # L2 业务编排 f01–f17（见 features/README.md）
├── http/                     # L3 HTTP 传输（见 http/README.md）
├── shared/                   # 跨层工具（见 shared/README.md）
├── scripts/                  # 运维 + 验收（见 scripts/README.md）
├── web/                      # L3 React 前端（见 web/README.md）
└── sim/<story_id>/           # 运行时产物（world.db / ipc / env_status.json，gitignore）
```

> 根目录三个 shim（`run_drama.py` / `routes.py` / `game_service.py`）只做转发/再导出，
> 业务实现都在 `core/`、`features/`、`http/`。

---

## Feature 速查表（F00–F17）

| ID | 名称 | 位置 | 职责 |
|----|------|------|------|
| **F00** | 平台 Runner | `core/runner/` | 仿真内核、Agent LLM、IPC、常驻 world loop |
| **F01** | 会话与重开 | `features/f01_session/` | DramaSession、Flask session、RESET_WORLD |
| **F02** | 玩家回合 API1 | `features/f02_player_turn/` | 打分→路由→inject；turn_pipeline |
| **F03** | 动作结果 API2 | `features/f03_action_result/` | 完成判定；world_loop 时委托 F14 |
| **F04** | 数值与打分 | `features/f04_stats/` | Stats 四维 LLM 打分 |
| **F05** | 剧情路由 | `features/f05_story_routing/` | Phase 节点 A/B/C/D、RoutingWatcher、结局裁定 |
| **F06** | 只读世界模型 | `features/f06_read_model/` | ReadOnlyWorldDB（queries/ 子模块） |
| **F07** | ABCS Agent 控制 | `features/f07_agent_control/` | 选角(L3)、story knowledge(L4)、对话节奏 |
| **F08** | HTTP 传输 | `http/` | Blueprint、IPC 客户端、健康、WS |
| **F17** | 虚拟玩家 | `features/f17_virtual_player/` | 玩家作为 agent 0、F2F 注入 |
| **F09** | 前端 UI | `web/src/features/` | 双栏世界舞台 + 剧情模式 |
| **F10** | 运维 | `scripts/ops/`、`scripts/tests/` | start/stop、验收 |
| **F11** | 回合内增量 | `features/f11_live_turn_sync/` | 后台异步 inject、task_state |
| **F12** | 世界 UI 同步 | `features/f12_world_sync/` | snapshot + delta + 四房间格式化 |
| **F13** | Loop 控制 | `features/f13_world_loop_control/` | pause/resume/resume_if_paused |
| **F14** | 常驻 delta | `features/f14_world_delta/` | `/world-delta` 轮询 + 路由扫描 + 结局 |
| **F15** | Prompt 追溯 | `features/f15_prompt_trace/` | LLM trace 审计 + Inspector |
| **F16** | WS 推送 | `features/f16_world_stream/` + `http/ws.py` | WebSocket world-stream |

> 注：曾用的 `f08_virtual_player/` 兼容 shim 已删除，虚拟玩家统一为 **F17**；
> **F08 专指 HTTP 传输（`http/`）**。

---

## HTTP API

前缀：`/api/drama/simulations/<story_id>/`（`story_id` 在大厅选/建并激活后动态确定，默认
`canglan_sword`；另有不带 `<story_id>` 的大厅端点 `/api/drama/lobby/*`。端点细节见
[`http/README.md`](http/README.md)）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `session/start` | 初始化 Flask session（必要时自动 resume loop） |
| POST | `session/reset` | 重开（IPC RESET + session 清零） |
| GET | `session` | 当前 stats / phase / turn |
| GET | `health` | Runner + world.db 就绪探针 |
| GET | `env-status` | Runner tick / loop 状态 |
| POST | `player-turn` | API 1：玩家台词 → 打分 + inject |
| GET | `action-result` | API 2 轮询（world_loop 时同 world-delta） |
| GET | `world-snapshot` | F12 全量世界快照 |
| GET | `world-delta?since_tick=` | F14 增量同步（路由/结局也走此处） |
| GET/POST | `world-loop/status\|pause\|resume` | F13 loop 控制 |
| GET | `prompt-trace/*` | F15 Prompt Inspector |
| POST | `debug-inject` | 调试 inject |

---

## 游戏流程（可玩范围）

| 阶段 | Turn | 说明 |
|------|------|------|
| Phase 1 | 1–4 | 前台接待破局；前台向 Jensen 简报、批准访客（节点 A → Phase 2） |
| Phase 2 | 5–12 | Jensen 私密审查；Tech VP 正面评估（节点 B → Phase 3） |
| Phase 3 | 13–20 | 谈判室；Turn 16 AMD 广播 + Sam；Jensen 清场 CEO（节点 C → Phase 4） |
| Phase 4 | 21–25 | 终局 1v1 谈 offer；**谈成即结束**（节点 D / 早结局），否则 Turn 25 裁定 |

**结局裁定（节点 D）**：Phase 4 中一旦谈成（Jensen 给出 offer 且玩家接受，由 F05
经 LLM 判定）即触发对应结局；否则到 Turn 25 由 LLM 意图分类 + trust 阈值裁定：

- `ending_join_nvidia` / `ending_seed_round` / `ending_cold_deal`

单回合含多次 LLM 调用，墙钟约 **15–90 秒**。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 四层架构、依赖硬规则、运行时数据流、tick/路由/结局机制 |
| [`config/prompts/README.md`](config/prompts/README.md) | L0：Agent prompt / 路由 / 虚拟玩家 YAML 布局 |
| [`core/runner/README.md`](core/runner/README.md) | L1 Runner：各文件职责、boot 流程、integration 桥 |
| [`features/README.md`](features/README.md) | L2：f01–f17 每个 Feature 的功能与内部文件作用 |
| [`http/README.md`](http/README.md) | L3 HTTP：路由/端点、IPC 客户端、WS、健康、错误 |
| [`shared/README.md`](shared/README.md) | 跨层工具各文件 |
| [`web/README.md`](web/README.md) | 前端结构、features/store/api、运行 |
| [`scripts/README.md`](scripts/README.md) | 运维脚本与验收测试 |

---

## 维护约定

- **不要**在根目录新增业务 `.py`；新能力放入对应 `features/fXX_*` 或 `core/runner/`。
- 改 Agent prompt 只动 `config/prompts/` 与各 Feature `config.py`，勿把 YAML 放回 `features/` 根目录。
- 提交前跑门禁：`python3 scripts/test_m0_acceptance.py` 与 `cd web && npm run build`。
- 依赖边界见 [`ARCHITECTURE.md`](ARCHITECTURE.md)（L3→L2、L1 经 integration、前端 app→features→shared）。
