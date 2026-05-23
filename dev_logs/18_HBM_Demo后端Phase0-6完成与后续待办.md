# 开发日志 18：HBM Demo 后端 Phase 0–6 完成与后续待办

**记录时间**：2026-05-23  
**分支**：`jensen-hwang-demo`（最新提交 `f228841` — Phase 6 交付收尾）  
**应用目录**：`agent_world/hbm_demo/`  
**详细后续规划**：`agent_world/hbm_demo/PLAN2.md`

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

### 1.2 验收测试（2026-05-23）

对 Phase 1–6 运行临时验收脚本 **23/23 通过**（脚本已删除，不纳入版本库）：

- Runner IPC：LIST_PLACES、MOVE_AGENT、env_status 含 `current_tick`
- Flask：debug-inject、session/start、Turn 4 Bad End、player-turn → action-result
- 单元：路由节点条件、Turn 16 payload、HTTP 错误映射、Phase 6 health/session
- 远程：已 push 至 `origin/jensen-hwang-demo`

### 1.3 明确不在 MVP 后端范围（已实现决策）

- 前端 UI（仅 API 契约就绪）
- 修改 `agent_world/demo/` 与引擎核心
- `state_updates` / NPC 内心 OS 上帝视角 API 字段
- 关系类型引擎级注册（MVP 用 fallback meta）
- PlaceMutation 跨进程持久化（进程内有效，Runner 重启后丢失）

---

## 2. 已知问题与后端可选优化

以下**不阻塞**前端开发，但影响线上体验，记录在案：

| # | 问题 | 现状 | 建议 |
|---|------|------|------|
| B-1 | **API 2 超时与默认 tick_count 不对齐** | 架构文档写 `current_tick >= start_tick + 8` 为兜底；默认 inject `tick_count=6` 仅推进 6 tick。若 NPC 未产生 F2F/RDC/GRP，轮询可能长期 `processing` | 前端传 `tick_count: 8`；或后端改 `check_action_complete` 与默认 tick 对齐（见 PLAN2 Phase B-1） |
| B-2 | **Flask 侧 LLM 打分偶发超时** | `score_player_turn` / `generate_immediate_msg` 失败时回退启发式/占位句 | 生产环境保证 `DMXAPI_KEY` 与网络；前端展示占位句即可 |
| B-3 | **Runner Agent LLM 延迟** | 单回合 inject 含多 Agent 决策，墙钟约 15–60s | 前端 loading + 双段式 UX（immediate_msg 先展示） |
| B-4 | **PlaceMutation 非持久** | 节点 B 的 `behavior_hint` 仅 Runner 进程内存有效 | MVP 可接受；重启 Runner 需重新 playthrough 至节点 B |
| B-5 | **P5-5 未做完整人工试玩** | 未系统走查 25 Turn 全路径 | 前端联调完成后按 PLAN2 验收清单执行 |
| B-6 | **无永久自动化测试入库** | PLAN 原策略「暂不写测试代码」 | PLAN2 建议 CI 集成轻量 smoke test |

---

## 3. 待完成工作总览（按优先级）

### 3.1 必须完成 — 本地一行命令可玩（见 PLAN2 F0–F6）

1. **前端 Web 应用**（`agent_world/hbm_demo/web/`）
   - 三屏布局：Stats / F2F 主对话 / RDC+GRP 上帝视角
   - 双段式：immediate_msg → action-result 轮询
   - Bad End 与 Turn 25 结局页
2. **Vite dev proxy**（`/api` → Flask:5000，**无需 CORS 补丁**）
3. **一行命令启动**：`./agent_world/hbm_demo/scripts/start_demo.sh`
   - 自动拉起 Runner + Flask + 前端 dev server
4. **环境**：Python 3.10+、Node 18+、`DMXAPI_KEY`

### 3.2 不在当前范围

- Docker / Nginx / 生产部署 / CI
- PR 合并、Release Tag（可后续单独做）

### 3.3 可选迭代（F7+，不影响本地可玩）

- `state_updates` 内心 OS 面板
- `PLAYTHROUGH.md` 25 轮参考台词
- localStorage 聊天历史缓存
- 前端 Vitest 单测

---

## 4. 前端需对接的后端 API 清单

前缀：`/api/hbm/simulations/hbm_memory_war/`  
Base URL 示例：`http://127.0.0.1:5000`

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `health` | 进入游戏前探针；503 = Runner 未起 |
| POST | `session/start` | 新游戏；需 `credentials: include` |
| GET | `session` | 刷新/恢复页面状态 |
| POST | `player-turn` | 玩家输入；见 API 1 三种响应 |
| GET | `action-result?task_id=` | 轮询；`status: processing \| completed` |
| GET | `env-status` | 可选：展示 current_tick（调试/上帝视角） |

**player-turn 请求体**：

```json
{
  "player_text": "…",
  "tick_count": 8
}
```

`place_id` / `phase` / `player_turn` 可传但**仅作展示**；后端以 Flask session 为准。

**player-turn 响应分支**：

| `data.status` | 前端行为 |
|---------------|----------|
| `processing` | 展示 `immediate_msg`，轮询 `action-result` |
| `game_over` | Bad End 页，`ending_id: bad_reject` |
| `completed` | Turn 25 结局页，无需 API 2 |

---

## 5. 与历史 dev_logs 的关系

| 文档 | 关系 |
|------|------|
| `dev_logs/03_Web端Demo游玩形式与UI设计方案.md` | 三屏布局、双段式 UX 的**产品设计源**；PLAN2 据此落地 |
| `dev_logs/17_HBM_Demo实现注意事项.md` | Tick 并发、Session 权威、节点 B 顺序；**后端已实现** |
| `dev_docs/1_story_prototype.md` | Phase/Turn 剧情与路由条件 |
| `dev_docs/2_architecture.md` | API 契约与 Stats 规则 |
| `agent_world/hbm_demo/PLAN.md` | Phase 0–6 后端规划（**已完成**） |
| `agent_world/hbm_demo/PLAN2.md` | **后续前端 + 部署 + 可选后端** 详细规划 |

---

## 6. 下一步行动（执行顺序，与 PLAN2 对齐）

1. **F0** — 初始化 `web/` + Vite proxy  
2. **F1** — API Client 层  
3. **F2** — 三屏 UI 壳  
4. **F3** — 游戏主循环，手动三进程跑通 Turn 1  
5. **F4** — 消息 / Stats / 结局 UI  
6. **F5** — 错误与 loading  
7. **F6** — `scripts/start_demo.sh` 一行启动 + 附录 D 验收  

---

*本日志与 PLAN2 同步维护；后端 Phase 0–6 无新增代码任务时，以 PLAN2 为唯一执行入口。*
