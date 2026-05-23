# 开发日志 18：HBM Demo 后端 Phase 0–6 与前端 F0–F6 完成

**记录时间**：2026-05-23（F6 更新）  
**分支**：`jensen-hwang-demo`  
**应用目录**：`agent_world/hbm_demo/`  
**详细规划**：后端 `PLAN.md` · 前端 + 一键启动 `PLAN2.md`

---

## 1. 已完成工作摘要

### 1.1 后端里程碑（Phase 0–6，全部完成）

| Phase | 内容 | 关键产出 |
|-------|------|----------|
| 0 | 脚手架与配置 | `hbm_scenario.yaml`、`run_hbm.py`、IPC stub、env_status merge |
| 1 | Runner 完整管线 | `HbmAgent`、`WorldStep`、inject tick 循环、`broadcast_helper` |
| 2 | Flask IPC 层 | `ipc_helper.py`、`game_service` 骨架、`routes.py`、`session/start` |
| 3 | API 1 / API 2 | 打分、Turn 4 Bad End、action-result 轮询、id→name |
| 4 | 四 Phase 剧情 | `routing.py` 节点 A/B/C/D、Turn 16 广播 + Sam、Turn 25 结局 |
| 5 | 打磨与联调 | `errors.py` / `settings.py`、HTTP 504/502/503、日志、README |
| 6 | 交付收尾 API | `health.py`、`GET /session`、`GET /health` |

### 1.2 前端里程碑（F0–F6，全部完成）

| Phase | 内容 | 关键产出 |
|-------|------|----------|
| F0 | 脚手架 | Vite + React + TS、三栏壳、`/api` proxy |
| F1 | API Client | `src/api/` 五端点、503/504 错误映射 |
| F2 | 三屏 UI 壳 | Stats / F2F / RDC+GRP、Mock 数据 |
| F3 | 游戏主循环 | `gameStore`、`useGameLoop`、session 持久化修复 |
| F4 | 消息 / Stats / 结局 | `MessageBubble`、`PhaseToast`、Stats pulse |
| F5 | 错误与 loading | Runner 503 Modal、poll 超时、env-status 底栏 |
| F6 | 一行启动 + 验收 | `scripts/start_demo.sh`、`stop_demo.sh`、`.env.example` |

### 1.3 本地可玩 Definition of Done（PLAN2 §〇）

在**仓库根目录**执行：

```bash
./agent_world/hbm_demo/scripts/start_demo.sh
```

即可启动 Runner + Flask + 前端，浏览器访问 `http://localhost:5173` 完成 Turn 1 双段式游玩（immediate_msg → action-result 轮询）。

### 1.4 验收测试（2026-05-23）

- 后端 Phase 1–6：**23/23** 通过（临时脚本已删除）
- 前端 F0–F5：**完整集成 + Turn 1 E2E** 通过（临时脚本已删除）
- 前端 F6：**附录 D 自动化项** 通过（临时脚本已删除）

### 1.5 明确不在 MVP 范围

- Docker / Nginx / 生产部署 / CI
- `state_updates` 内心 OS 上帝视角 API
- 刷新后聊天记录持久化（可选 F9 localStorage）
- 25 Turn 完整主线路人工试玩文档（可选 F8 `PLAYTHROUGH.md`）

---

## 2. 已知问题与可选优化

| # | 问题 | 现状 | 建议 |
|---|------|------|------|
| B-1 | API 2 超时与默认 tick_count | 前端固定传 `tick_count: 8` | 已在前端 `useGameLoop` 实现 |
| B-2 | Flask LLM 打分偶发超时 | 回退启发式 / 占位句 | 保证 `DMXAPI_KEY` 与网络 |
| B-3 | Runner Agent LLM 延迟 | 单回合 15–60s | 前端 loading + immediate_msg |
| B-4 | PlaceMutation 非持久 | 重启 Runner 后丢失 | MVP 可接受 |
| B-5 | 25 Turn 全路径未系统试玩 | F6 仅验 Turn 1 | 可选 F8 参考台词 |
| B-6 | 无永久自动化测试入库 | 各阶段临时脚本验收后删除 | 可选 F10 Vitest / CI smoke |

---

## 3. 前端 API 清单

前缀：`/api/hbm/simulations/hbm_memory_war/`（Vite dev proxy → Flask:**5050**）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `health` | 进入游戏前探针；503 = Runner 未起 |
| POST | `session/start` | 新游戏；需 `credentials: include` |
| GET | `session` | 刷新/恢复 stats / phase / turn |
| POST | `player-turn` | 玩家输入；见 API 1 三种响应 |
| GET | `action-result?task_id=` | 轮询 |
| GET | `env-status` | Observer 底栏 current_tick（F5） |

**player-turn 请求体**：`{ "player_text": "…", "tick_count": 8 }`

---

## 4. 与历史 dev_logs 的关系

| 文档 | 关系 |
|------|------|
| `dev_logs/03_*` | 三屏布局、双段式 UX 设计源 |
| `dev_logs/17_*` | Tick 并发、Session 权威；后端已实现 |
| `dev_docs/1_story_prototype.md` | Phase/Turn 剧情 |
| `dev_docs/2_architecture.md` | API 契约与 Stats 规则 |
| `PLAN.md` | 后端 Phase 0–6（**已完成**） |
| `PLAN2.md` | 前端 F0–F6（**已完成**） |

---

## 5. 下一步（可选 F7+）

1. **F7** — `state_updates` 内心 OS 面板  
2. **F8** — `web/PLAYTHROUGH.md` 25 轮参考台词  
3. **F9** — localStorage 聊天历史缓存  
4. **F10** — Vitest 单测 / CI smoke  

---

*本日志与 PLAN2 同步维护；F0–F6 完成后以可选 F7+ 为后续入口。*
