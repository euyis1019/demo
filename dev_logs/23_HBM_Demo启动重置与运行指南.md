# 开发日志 23：HBM Demo 启动、重置与运行指南

**记录时间**：2026-05-24  
**分支**：`jensen-hwang-demo`  
**应用目录**：`agent_world/hbm_demo/`  
**关联文档**：
- 目录结构 → [`22_HBM_Demo目录结构与功能说明.md`](./22_HBM_Demo目录结构与功能说明.md)
- 25 轮试玩台词 → [`19_HBM_Demo_25轮参考台词.md`](./19_HBM_Demo_25轮参考台词.md)

---

## 1. 环境前提（首次使用前）

在**仓库根目录**执行一次依赖安装：

```bash
cd /path/to/demo          # 仓库根
pip install -e .          # 或 uv sync
```

| 依赖 | 要求 | 说明 |
|------|------|------|
| Python | 3.10+ | 需能 `import agent_world` |
| Node.js | 18+ | 前端 Vite |
| `DMXAPI_KEY` | 必填（LLM 可用） | Runner Agent + Flask 打分 / immediate_msg |

配置 API Key（三选一）：

```bash
export DMXAPI_KEY=sk-your-key

# 或写入文件（start_demo.sh 会自动加载，已 export 的变量优先）
cp agent_world/hbm_demo/.env.example agent_world/hbm_demo/.env
# 编辑 .env：DMXAPI_KEY=sk-...

# 或写入 agent_world/demo/.env（与 demo 共用）
```

> **注意**：API 欠费或 Key 无效时，中屏 NPC 无回复、打分失败，表现为「只有玩家气泡」。请先确认 LLM 账户余额与 Key 有效。

---

## 2. 日常启动（推荐 · 一行命令）

**工作目录：仓库根目录**

```bash
./agent_world/hbm_demo/scripts/start_demo.sh
```

脚本行为：

1. 自动 `stop_demo.sh` 清理残留进程  
2. 后台启动 **Runner**（`run_hbm`）  
3. 后台启动 **Flask**（端口 **5050–5059** 自动选取空闲，避开 macOS 5000）  
4. 前台启动 **Vite** 前端（默认 **5173**）  
5. macOS 下约 2s 后自动打开浏览器  

成功时终端输出类似：

```text
HBM Demo 已启动
  Runner : OK
  Flask  : http://127.0.0.1:5050
  前端   : http://localhost:5173
按 Ctrl+C 停止全部进程
```

浏览器访问：**http://localhost:5173** → 点击「开始游戏」→ 输入台词游玩。

---

## 3. 停止

### 3.1 正常停止

在运行 `start_demo.sh` 的终端按 **Ctrl+C**，脚本会自动调用 `stop_demo.sh` 清理 Runner / Flask / Vite。

### 3.2 手动停止（脚本异常退出时）

```bash
./agent_world/hbm_demo/scripts/stop_demo.sh
```

可重复执行，无副作用。

---

## 4. 重置说明（两套状态要分开清）

Demo 有两套互不影响的状态：

| 状态 | 存储位置 | 影响 |
|------|----------|------|
| **游戏进度**（Stats / Phase / Turn / place_id） | 浏览器 **Flask Session Cookie** | 左栏数值、当前 Phase/Turn |
| **世界仿真**（Agent 位置、消息、Tick） | `sim/hbm_memory_war/world.db` + IPC | NPC 对话历史、World Tick |

只删 `world.db` **不会**清掉浏览器里的 Turn；只清 Cookie **不会**清掉 NPC 已写入的消息。

---

## 5. 完全重置后再启动（推荐流程）

适用于：想从 Turn 1 重新试玩、改过 `hbm_scenario.yaml`、或 world 状态混乱。

### 步骤 1 — 停止进程

```bash
./agent_world/hbm_demo/scripts/stop_demo.sh
```

### 步骤 2 — 确认 sim 目录指向仓库内路径

```bash
unset HBM_SIM_DIR
```

若曾 `export HBM_SIM_DIR=/tmp/...`，删错目录会导致「清了库但游戏还有旧进度」。

默认 sim 目录：

```text
agent_world/hbm_demo/sim/hbm_memory_war/
```

### 步骤 3 — 删除运行时产物

```bash
rm -rf agent_world/hbm_demo/sim/hbm_memory_war/world.db
rm -rf agent_world/hbm_demo/sim/hbm_memory_war/ipc
rm -f  agent_world/hbm_demo/sim/hbm_memory_war/env_status.json
```

或整目录清空后重建：

```bash
rm -rf agent_world/hbm_demo/sim/hbm_memory_war
mkdir -p agent_world/hbm_demo/sim/hbm_memory_war
```

### 步骤 4 — 清除浏览器 Session（任选其一）

| 方式 | 操作 |
|------|------|
| **A. 浏览器** | 开发者工具 → Application → Cookies → 删除 `localhost:5173` 相关 Cookie |
| **B. 无痕窗口** | 用新的无痕/隐私窗口打开 `http://localhost:5173` |
| **C. 游戏内** | 启动后点「重新开始」（会调 `POST session/start`） |

完全从零开始建议 **A 或 B**，最干净。

### 步骤 5 — 重新启动

```bash
./agent_world/hbm_demo/scripts/start_demo.sh
```

Runner 启动时会根据 `hbm_scenario.yaml` **重新 seed** 空的 `world.db`。

### 步骤 6 — 验证

1. 打开 http://localhost:5173  
2. 「开始游戏」→ 左栏应显示 Phase 1、Turn 1、初始 Stats  
3. 可选：`curl -s http://127.0.0.1:5050/api/hbm/simulations/hbm_memory_war/health` 应返回 `ready: true`

---

## 6. 一键复制：重置 + 启动

在**仓库根目录**可整段执行：

```bash
./agent_world/hbm_demo/scripts/stop_demo.sh
unset HBM_SIM_DIR
rm -rf agent_world/hbm_demo/sim/hbm_memory_war/world.db \
       agent_world/hbm_demo/sim/hbm_memory_war/ipc \
       agent_world/hbm_demo/sim/hbm_memory_war/env_status.json
./agent_world/hbm_demo/scripts/start_demo.sh
```

执行后请**清除浏览器 Cookie 或使用无痕窗口**，再点「开始游戏」。

---

## 7. 修改 yaml / 后端代码后

| 改动类型 | 需要做什么 |
|----------|------------|
| 修改 `hbm_scenario.yaml`（Agent prompt、地点等） | **必须重启 Runner**（stop → start；建议同时删 `world.db` 重新 seed） |
| 修改 `game_service.py` / `routes.py` 等 Flask 代码 | **必须重启 Flask**（stop → start 最简单） |
| 修改 `web/` 前端 | Vite 热更新；不生效则 Ctrl+C 后重新 `start_demo.sh` |
| 仅想新开一局（不改代码） | 浏览器清 Cookie 或「重新开始」；可选删 `world.db` |

---

## 8. 手动分进程启动（脚本失败时的 fallback）

三个终端，均在仓库根目录。

**终端 1 — Runner（必须先起）**

```bash
unset HBM_SIM_DIR
python -m agent_world.hbm_demo.run_hbm \
  --config agent_world/hbm_demo/hbm_scenario.yaml \
  --sim-dir agent_world/hbm_demo/sim/hbm_memory_war/
```

等待 `env_status.json` 中 `"status": "running"`。

**终端 2 — Flask**

```bash
export HBM_SIM_DIR=agent_world/hbm_demo/sim/hbm_memory_war/
export FLASK_APP=agent_world.app:create_app
flask run --host 127.0.0.1 --port 5050
```

**终端 3 — 前端**

```bash
cd agent_world/hbm_demo/web
npm install   # 首次
npm run dev
# http://localhost:5173
```

---

## 9. 健康检查与日志

### 9.1 HTTP 探针

```bash
# 双进程就绪（Runner + world.db 可读）
curl -s http://127.0.0.1:5050/api/hbm/simulations/hbm_memory_war/health | python -m json.tool

# 当前 World Tick
curl -s http://127.0.0.1:5050/api/hbm/simulations/hbm_memory_war/env-status
```

### 9.2 脚本日志

| 文件 | 内容 |
|------|------|
| `agent_world/hbm_demo/scripts/.run/runner.log` | Runner 输出 |
| `agent_world/hbm_demo/scripts/.run/flask.log` | Flask 输出 |
| `agent_world/hbm_demo/scripts/.run/demo.pids` | 后台进程 PID（stop 时使用） |

### 9.3 常见 HTTP 错误

| 状态码 | 含义 | 处理 |
|--------|------|------|
| 503 | Runner 未就绪或 DB locked | 确认 Runner 已启动；稍等重试 |
| 504 | IPC inject 超时（默认 600s） | 查看 runner.log；检查 LLM 网络 |
| 502 | IPC 返回 failed | 重启 Runner |

---

## 10. 环境变量速查

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HBM_SIM_DIR` | `agent_world/hbm_demo/sim/hbm_memory_war/` | ** unset 后使用仓库内路径** |
| `DMXAPI_KEY` | — | LLM API Key |
| `FLASK_RUN_PORT` | 5050（或 5050–5059 自动选） | Flask 端口 |
| `VITE_PORT` | 5173 | 前端端口 |
| `FLASK_APP` | `agent_world.app:create_app` | Flask 入口 |

---

## 11. curl 快速试玩 Turn 1（无浏览器）

```bash
# 初始化 session
curl -s -X POST http://127.0.0.1:5050/api/hbm/simulations/hbm_memory_war/session/start \
  -c /tmp/hbm_cookies.txt

# API 1
curl -s -X POST http://127.0.0.1:5050/api/hbm/simulations/hbm_memory_war/player-turn \
  -b /tmp/hbm_cookies.txt -H 'Content-Type: application/json' \
  -d '{"player_text":"我的算法能把显存消耗降低80%。","tick_count":8}'

# API 2（将 task_xxx 替换为上一步返回的 task_id，轮询至 status=completed）
curl -s "http://127.0.0.1:5050/api/hbm/simulations/hbm_memory_war/action-result?task_id=task_xxx" \
  -b /tmp/hbm_cookies.txt
```

单回合 LLM 决策约 **15–60 秒** 墙钟时间，属正常现象。

---

*文档版本：2026-05-24 · 与 `start_demo.sh` / `stop_demo.sh` 当前行为对齐。*
