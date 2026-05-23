# 开发日志 18：HBM Demo 后端 Phase 0–6 与前端 F0–F6 完成

**记录时间**：2026-05-23（F6 完成 · 限制项归档）  
**分支**：`jensen-hwang-demo`（最新提交 `92e4f8d`）  
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
| F6 | 一行启动 + 验收 | `scripts/start_demo.sh`、`stop_demo.sh`、`.env.example`、Flask **5050** 专用端口 |
| F8 | 25 轮参考台词 | `dev_logs/19_HBM_Demo_25轮参考台词.md`（2026-05-23） |

### 1.3 本地可玩 Definition of Done（PLAN2 §〇）

在**仓库根目录**执行：

```bash
./agent_world/hbm_demo/scripts/start_demo.sh
```

即可启动 Runner + Flask + 前端，浏览器访问 `http://localhost:5173` 完成 Turn 1 双段式游玩（immediate_msg → action-result 轮询）。

**结论（2026-05-23 核查）**：PLAN.md + PLAN2 **MVP 范围内开发已全部完成**；Demo 可正常本地游玩 Turn 1 及后续回合（需 `DMXAPI_KEY` 与 LLM 网络）。

### 1.4 验收测试（2026-05-23）

| 范围 | 结果 | 说明 |
|------|------|------|
| 后端 Phase 1–6 | **23/23** 通过 | 临时脚本已删除 |
| 前端 F0–F5 | Turn 1 E2E 通过 | 临时脚本已删除 |
| 前端 F6 | 附录 D 自动化项通过 | 含 start/stop、5050 端口、重复启动 |
| 前端 F0–F6 联调 | 全量通过 | 提交 `92e4f8d` 前最后一次验收 |

**验收范围边界**：自动化仅**系统验证 Turn 1**；25 Turn 全主线、Bad End / Turn 25 结局页的**端到端人工试玩**未纳入自动化（见 §3.2）。

---

## 2. 尚未完成的工作（非 MVP 阻塞）

以下项在 PLAN2 / PLAN 中**明确不在 MVP**，或标注为**可选**；不做也不影响「本地一行命令 + Turn 1 可玩」。

### 2.1 前端可选阶段（F7+）

| ID | 内容 | 说明 | 优先级 |
|----|------|------|--------|
| F7 | `state_updates` 内心 OS 面板 | 后端未暴露该 API 字段；上帝视角增强 | 低 |
| F8 | `dev_logs/19_HBM_Demo_25轮参考台词.md` | 25 轮参考台词 | ✅ 已完成 |
| F9 | localStorage 聊天历史 | 刷新后 messages 不丢（见 §4.1 #6） | 低 |
| F10 | Vitest 单测 / CI smoke | 永久自动化测试入库（见 §4.2 #B-6） | 低 |

### 2.2 后端可选优化（PLAN2 §七 B-2 / B-3）

| ID | 内容 | 现状 | 是否阻塞 |
|----|------|------|----------|
| B-2 | `game_service` 默认 `tick_count` 改为 8 | 仍为 6；前端已固定传 8 | 否 |
| B-3 | `check_action_complete` 在 `ipc_end_tick >= start+6` 且无消息时也 completed | 未改；依赖前端 `tick_count: 8` 兜底 | 否 |

### 2.3 交付与工程化（PLAN2 §1.3 不在范围）

| 项 | 说明 |
|----|------|
| Docker / docker-compose | 未做 |
| Nginx / 云部署 / 生产 WSGI | 未做 |
| GitHub Actions / pytest CI | 未做 |
| PR 合并 main / Release Tag | 未做（可后续单独处理） |
| 修改 `agent_world/demo/` 与引擎核心 | 未做且不在范围 |

### 2.4 MVP 后端明确不做项（已实现决策，仍属「未完成」清单）

| 项 | 说明 |
|----|------|
| `state_updates` / NPC 内心 OS API | 无后端字段 |
| 关系类型引擎级注册 | MVP 用 fallback meta |
| PlaceMutation 跨进程持久化 | 见 §4.2 #B-4 |
| 前端以外的永久 E2E 测试库 | 各阶段临时脚本验收后已删除 |

### 2.5 文档待同步（非功能缺口）

| 文档 | 问题 |
|------|------|
| — | PLAN2 §1.1 已更新为 F0–F6 ✅（2026-05-23） |

---

## 3. 验收与 DoD 差距说明

PLAN2 §〇 DoD 第四条写明：Stats / Phase / Turn 正常更新；**Turn 4 Bad End 与 Turn 25 结局页可触发**。

| DoD 子项 | 代码实现 | 自动化 / 人工验证 |
|----------|----------|-------------------|
| Turn 1 双段式游玩 | ✅ 前后端完整 | ✅ 自动化 E2E 已通过 |
| Stats / Phase / Turn 更新 | ✅ | ✅ Turn 1 已验 |
| Turn 4 Bad End | ✅ 前后端分支 `game_over` | ⚠️ **未做系统人工试玩** |
| Turn 25 结局页 | ✅ 前后端分支 `completed` + `EndingScreen` | ⚠️ **未做系统人工试玩** |
| 25 Turn 全主线 | ✅ 后端 routing 已实现 | ⚠️ **人工试玩待做**（台词见 `dev_logs/19_HBM_Demo_25轮参考台词.md`） |

---

## 4. 已知限制（游玩与运维）

### 4.1 设计与产品层限制

| # | 限制 | 影响 | 缓解 / 后续 |
|---|------|------|-------------|
| L-1 | **刷新页面后聊天消息丢失** | Flask session 仅存 stats / phase / turn，不存 messages | MVP 可接受；F9 localStorage |
| L-2 | **单回合墙钟延迟 15–90s** | Runner 多 Agent LLM 决策 + IPC inject | 前端 loading、`immediate_msg` 双段式 UX |
| L-3 | **poll 最多 120×1.5s** | 极端情况下 NPC 仍未 completed 会超时提示 | F5 已实现 `POLL_TIMEOUT_MESSAGE`；确认 Runner 运行 |
| L-4 | **需有效 `DMXAPI_KEY`** | 无 Key 时打分 / NPC 可能失败或占位 | `.env.example` + README 说明 |
| L-5 | **脚本不安装依赖** | 须事先 `pip install -e .`、`Node 18+` | README / start_demo 启动前检测 |

### 4.2 后端与运行时限制

| # | 限制 | 影响 | 缓解 / 后续 |
|---|------|------|-------------|
| B-1 | API 2 超时与默认 `tick_count` 不对齐 | 后端默认 inject 6 tick；架构文档写 +8 兜底 | **前端已固定 `tick_count: 8`** |
| B-2 | Flask 侧 LLM 打分偶发超时 | 回退启发式 / 占位 `immediate_msg` | 保证 Key 与网络 |
| B-3 | Runner Agent LLM 延迟 | 见 L-2 | 同 L-2 |
| B-4 | **PlaceMutation 非持久** | 节点 B 的 `behavior_hint` 仅 Runner 进程内有效；**重启 Runner 后丢失** | 重启后需重新 playthrough 至节点 B |
| B-5 | **25 Turn 全路径未系统试玩** | F8 台词已就绪；人工按 PLAYTHROUGH 走查仍待做 | 见 `dev_logs/19_HBM_Demo_25轮参考台词.md` |
| B-6 | **无永久自动化测试入库** | 回归依赖手动或临时脚本 | F10 Vitest / CI smoke |

### 4.3 环境与端口

| # | 限制 | 说明 |
|---|------|------|
| P-1 | Flask 专用端口 **5050**（5050–5059 自动选取） | 避开 macOS AirPlay 占用的 **5000**；见 `scripts/demo_ports.sh` |
| P-2 | 前端 dev **5173** | Vite `strictPort`；冲突时需 `export VITE_PORT=` |
| P-3 | 双进程顺序 | 须 Runner 与 Flask 共用同一 `HBM_SIM_DIR`；`start_demo.sh` 已按序拉起 |
| P-4 | `player-turn` 可能耗时数分钟 | 前端不设短 timeout；后端 `HBM_IPC_TIMEOUT` 默认 600s |

### 4.4 游玩能力边界（用户预期管理）

| 能力 | 状态 |
|------|------|
| 本地 Turn 1 完整游玩 | ✅ 已验收 |
| 多 Turn 连续游玩（API 层面） | ✅ 代码支持；未全路径人工验证 |
| Turn 4 Bad End 触发 | ✅ 代码支持；建议人工验证一次 |
| Turn 25 三结局触发 | ✅ 代码支持；建议人工验证 |
| 刷新恢复 Stats/Turn | ✅ `GET /session` |
| 刷新恢复聊天记录 | ❌ 不支持（L-1） |
| 内心 OS 上帝视角 | ❌ F7 未做 |
| 生产环境一键部署 | ❌ 不在 MVP |

---

## 5. 前端 API 清单

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

## 6. 与历史 dev_logs 的关系

| 文档 | 关系 |
|------|------|
| `dev_logs/03_*` | 三屏布局、双段式 UX 设计源 |
| `dev_logs/17_*` | Tick 并发、Session 权威；后端已实现 |
| `dev_docs/1_story_prototype.md` | Phase/Turn 剧情 |
| `dev_docs/2_architecture.md` | API 契约与 Stats 规则 |
| `PLAN.md` | 后端 Phase 0–6（**已完成**） |
| `PLAN2.md` | 前端 F0–F6（**已完成**） |
| `dev_logs/19_*` | 25 轮参考台词（F8 PLAYTHROUGH） |

---

## 7. 建议后续行动（按优先级）

1. **人工试玩**：按 `dev_logs/19_HBM_Demo_25轮参考台词.md` 走通 25 Turn + Bad End / 三结局验证  
2. ~~**F8**~~：参考台词见 `dev_logs/19_HBM_Demo_25轮参考台词.md`  
3. **文档**：更新 `PLAN2.md` §1.1 状态为 ✅  
4. **可选**：F9 聊天缓存、F7 内心 OS、F10 测试入库、B-2/B-3 后端双保险  

---

*本日志为 HBM Demo MVP 交付与限制的单一归档入口；功能开发以 PLAN2 F7+ 为可选延续。*
