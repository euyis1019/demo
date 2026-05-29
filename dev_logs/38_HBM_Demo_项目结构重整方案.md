# 38 — HBM Demo 项目结构重整方案（完整版）

> **分支**：`hbm-demo-restructure`（自 `jensen-hwang-demo` 拉出）  
> **日期**：2026-05-23  
> **前置**：[`37_HBM_Demo_代码重整与清理记录.md`](./37_HBM_Demo_代码重整与清理记录.md)（dead code 清理已完成）  
> **依据**：[`26_HBM_Demo_Feature规划与代码结构重整方案.md`](./26_HBM_Demo_Feature规划与代码结构重整方案.md)（四层架构与 Feature 定义）  
> **状态**：**Phase R0–R4 已落地 · R5 可选待做**

---

## 一、文档目的

在 **37 号清理**（删除 hardening / legacy / 孤儿 UI）之后，Demo 运行时已无已知遗弃代码。下一阶段目标是 **项目结构重整**：

1. 对齐 **仓库级** 四层边界（L0–L3、Runner、HTTP、测试目录）。
2. 对齐 **Feature 内部** 模块规范（handler / service / models / config 分层）。
3. 消除开发过程中积累的 **跨 Feature 渗血、Fat Handler、命名冲突**。
4. 产出可逐 PR 落地的迁移计划，每步以 `test_m0_acceptance.py` + `npm run build` 门禁。

本文档为结构重整的 **唯一实施依据**；与 26 号文档关系：26 定义「拆什么 Feature」，38 定义「Feature 内外怎么摆、怎么迁」。

---

## 二、外部规范参考（重整原则来源）

以下规范来自 Flask / Python 模块化单体与 React Feature 架构的业界共识，用于校正当前 Demo 的「能跑但不规范」之处。

### 2.1 后端（Flask / 模块化单体）

| 原则 | 来源 | 对本 Demo 的含义 |
|------|------|------------------|
| **按业务域分包，不按技术类型分包** | [Flask Blueprint Patterns](https://reintech.io/blog/flask-blueprint-patterns-large-applications)、[Miguel Grinberg — Application Structure](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xv-a-better-application-structure) | 每个 `features/fNN_*` 是一个 Blueprint 级业务包；禁止回到「所有 routes 一个文件」 |
| **Thin Route / Fat Service** | [Deflating Flask Fat Routes](https://leapcell.io/blog/deflating-flask-fat-routes-a-guide-to-service-and-repository-layers)、[LaunchStack Flask SaaS Structure](https://launchstack.space/blog/flask-saas-project-structure-production-architecture) | `http/routes.py` 与 `handler.py` 只做参数解析 + 委托 + 错误映射；编排进 `service.py` |
| **Application Factory / 无全局状态** | Miguel Grinberg、Muneeb Dev Flask 结构指南 | Demo 已用 Blueprint；`game_service.py` 全局 barrel 应逐步退役 |
| **Blueprint 内相对导入、避免循环依赖** | Reintech Blueprint 模式 | Feature 对外只暴露 `__init__.py` 公共 API；Feature 间通过显式依赖或 `shared/` |
| **配置集中、不散落** | LaunchStack §Config | L0 yaml 物理位置可保留，但需 `config/manifest.yaml` 索引 |

### 2.2 前端（React Feature 模块）

| 原则 | 来源 | 对本 Demo 的含义 |
|------|------|------------------|
| **按 Feature 组织，不按 components/hooks 全局分** | [Robin Wieruch — React Folder Structure 2026](https://www.robinwieruch.de/react-folder-structure/)、[Modular Feature Design](https://www.codewithseb.com/blog/modular-feature-design-react-plug-and-play) | `web/src/features/<name>/` 拥有 UI + hooks + 局部 utils；全局仅 `api/`、`store/`、`shared/` |
| **Colocation（同改同目录）** | [Frontend Architecture Playbook](https://github.com/khasky/frontend-architecture-playbook) | 与组件紧耦合的 hook/util 不放到顶层 `utils/` |
| **Public API via index.ts** | Code With Seb、FSD public-api 规则 | 外部只 `import from '@/features/world-stage'`，禁止 deep import 内部文件 |
| **依赖方向：app → features → shared** | Feature-Sliced Design、[eslint boundaries 实践](https://dev.to/vavilov2212/enforce-module-imports-in-fsd-using-eslint-plugin-import-2d72) | `shared/` 不得 import features；跨 Feature 须显式声明 |
| **单文件 ~300–400 行上限** | React Folder Patterns colocation 指南 | 超过则拆子组件或抽 hook（如 `conversation_control.py` 804 行） |

### 2.3 提炼为本项目的 **Feature 内部标准模板**

每个后端 Feature（有 HTTP 或 Runner 触点的）目标结构：

```text
features/fNN_<name>/
├── __init__.py          # 公共 API（__all__ 白名单）
├── handler.py           # 传输层入口：Flask/IPC 参数 → service（≤80 行理想）
├── service.py           # [新建/迁移] 业务编排（可测，无 Flask request）
├── models.py            # 领域模型 / dataclass（可选）
├── schemas.py           # [可选] 请求/响应形状、常量键名
├── config.py            # [可选] 读本 Feature yaml
├── config.yaml          # [可选] Feature 专属配置（colocate）
├── adapters/            # [可选] IPC、DB、跨 Feature 调用封装
│   └── ipc.py
└── tests/               # [远期] Feature 单测（Phase R1 后可建）
```

前端 Feature 目标结构：

```text
web/src/features/<name>/
├── index.ts             # 唯一公共出口
├── components/          # 仅本 Feature 的 UI
├── hooks/
├── lib/                 # 纯函数、布局算法
└── types.ts             # [可选]
```

---

## 三、现状诊断（清理后，2026-05-23）

### 3.1 仓库级结构债

| # | 问题 | 典型位置 | 严重度 |
|---|------|----------|--------|
| A | **L1 `core/runner/` 直接 import L2 `features/`** | `world_step.py`、`world_loop.py`、`hbm_agent.py` 等 | 高 |
| B | **`game_service.py` 仍为万能 barrel** | 118 行，聚合 F01–F04、F06、F12–F15 | 中 |
| C | **F08 编号冲突** | Registry F08=HTTP，F08V=虚拟玩家 | 中 |
| D | **F16 WS 注册在 `agent_world/app/__init__.py`** | 非 `http/` | 中 |
| E | **前后端 FEATURE_REGISTRY 不一致** | 后端 18 项；前端缺 F11/F13–F16、prompt-trace | 低 |
| F | **测试 monolith** | `test_m0_acceptance.py` ~4300 行 | 中 |
| G | **文档滞后** | dev_logs/26 仍写三栏 UI、F07 默认关闭 | 低 |

### 3.2 跨 Feature 依赖图（问题热点）

```text
f02_handler ──→ f01, f04, f05, f06, f07, f08V, f11, f13, http.ipc
f03_handler ──→ f01, f02, f04, f06, f07, f11, f12, f14（world_loop 时整段委托）
f11_async_inject ──→ 几乎复制 f02 编排链
f05_watcher ──→ f12_formatter, f13_pause, f07, http.ipc
f12_formatter ──→ f03_completion（反向：展示层依赖 API2 格式化）
f12_delta ──→ f02, f03, f06, f15
f14_handler ──→ f05_watcher, f12_delta（薄封装）
f16_handler ──→ f14
```

**结论**：F02/F11 重复、F03↔F14 职责重叠、F05↔F12 格式化耦合是 Feature 内/间重整的首要目标。

### 3.3 各 Feature 内部审计

> 行数为 2026-05-23 统计；「违规」指相对 §2.3 模板的偏差。

#### F01 — 会话与重开 `features/f01_session/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `models.py` | 小 | HbmSession | ✅ |
| `lifecycle.py` | 中 | CRUD | ✅ |
| `reset.py` | 中 | Flask reset | ⚠️ 直接 import F11 `clear_async_state` |
| `world_reset.py` | 139 | Runner RESET + F15 purge | ⚠️ Runner 侧与 Flask 侧 reset 同 Feature 但无 `service.py` 统一 |
| `paths.py` / `constants.py` | 小 | L0 路径 | ✅ |

**重整建议**：
- 新增 `service.py`：`reset_session_flask()` / `reset_world_runtime()` 统一编排。
- `reset.py` / `world_reset.py` 降为 adapter（Flask / IPC 入口）。
- F11 清理通过 **事件钩子** 或 `f01/adapters/async_state.py` 显式调用，避免 reset 散落 import。

#### F02 — 玩家回合 `features/f02_player_turn/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `handler.py` | **515** | API1 全编排 | ❌ Fat Handler：打分、路由、IPC、F11 分支、F08V、F13 暂停 |
| `inject.py` | 中 | inject 事件构建 | ⚠️ 含 `check_turn4_bad_end`（agent_driven 下恒 false） |
| `task.py` | 小 | PendingTask | ✅ |

**重整建议**：
- 拆 `service.py`：`execute_player_turn(session, text) -> TaskResult`。
- 拆 `adapters/ipc.py`：enqueue / inject_batch / mirror 推送。
- `handler.py` 保留 HTTP 绑定 + 异常映射（目标 ≤80 行）。
- world_loop 开启时走 F11 的路径收拢到 **单一策略函数**（与 F11 共用）。

#### F03 — 动作结果 `features/f03_action_result/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `handler.py` | 150 | API2 | ❌ world_loop 启用时 **整段委托 F14**，F03 名存实亡 |
| `completion.py` | 172 | 完成判定 + `format_messages` | ⚠️ `format_messages` 被 F12 依赖，职责越界 |

**重整建议**：
- 将 `format_messages` 迁至 `shared/messages.py` 或 `f12/lib/message_format.py`（F12 消费）。
- `handler.py` 在 world_loop 模式下改为 **明确 adapter**（文档化「API2 兼容层 → F14」），或 HTTP 层直接路由到 F14。
- `completion.py` 仅保留「完成判定」逻辑。

#### F04 — 数值与打分 `features/f04_stats/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `scoring.py` | 147 | LLM/heuristic 打分 | ✅ 结构清晰 |
| `deltas.py` | 小 | Stats 更新 | ✅ |

**重整建议**：维持现状；可选增加 `service.py` 封装 `score_and_apply()` 供 F02/F11 调用。

#### F05 — 剧情路由 `features/f05_story_routing/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `routing.py` | **389** | Phase 节点、inject 目标 | ⚠️ 偏大，可按 Phase 拆 `routing_phases.py` |
| `routing_config.py` | 小 | yaml 加载 | ✅ |
| `agent_signals.py` | 228 | bad_end 检测 | ✅ |
| `story_signals.py` | 小 | DB signal | ✅ |
| `watcher.py` | 183 | F14 侧路由扫描 | ❌ 依赖 F12 formatter、F13 pause、http.ipc |

**重整建议**：
- `watcher.py` 产出 **原始 routing 事件**；格式化交给 F12 或 `shared/routing_events.py`。
- 暂停 loop 改为调用 F13 **公共 API**（经 `f13/__init__.py`），禁止 deep import handler。
- Registry `modules` 补全：`routing_config`, `agent_signals`, `story_signals`, `watcher`。

#### F06 — 只读世界模型 `features/f06_read_model/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `world_db.py` | **637** | 全部 DB 只读查询 | ❌ God Module |

**重整建议**（Phase R5 或独立 PR）：

```text
f06_read_model/
├── world_db.py          # Facade：make_readonly_db() 不变
├── queries/
│   ├── messages.py      # F2F / thread
│   ├── moves.py         # 位置历史
│   ├── rdc.py           # RDC 连接
│   └── grp.py           # 群聊
└── display_names.py     # sender_display_name
```

对外 `__init__.py` 保持原 export，内部拆分。

#### F07 — ABCS `features/f07_agent_control/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `conversation_control.py` | **804** | 对话控制 | ❌ 必须拆分 |
| `knowledge.py` | 324 | L3 知识注入 | ⚠️ |
| `pick_active.py` | 311 | 活跃 Agent 选择 | ⚠️ |
| `config.py` | 127 | turn_control yaml | ✅ |
| `story_knowledge/` | 多 yaml | 配置 colocate | ✅ 良好实践 |
| 其余 | 中 | turn_context, inject_batch… | 基本合理 |

**重整建议**：

```text
f07_agent_control/
├── __init__.py              # 公共 API 不变
├── config.py
├── turn_control.yaml
├── runtime/                 # Runner 热路径
│   ├── turn_context.py
│   ├── pick_active.py
│   ├── inject_batch.py
│   ├── session_mirror.py
│   └── player_response.py
├── conversation/            # 从 conversation_control 拆出
│   ├── control.py           # 主入口（原 conversation_control 瘦身）
│   ├── f2f_rules.py
│   └── batch_rules.py
├── knowledge/               # Python 模块（非 yaml 目录）
│   ├── builder.py           # 原 knowledge.py
│   └── llm_params.py
└── story_knowledge/         # yaml 保持
```

Runner 侧仅通过 `core/runner/integration/abcs.py` 调用 `runtime/*` 公共 API。

#### F08V — 虚拟玩家 `features/f08_virtual_player/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| 全套 | <130/文件 | entity + f2f + config | ✅ **最佳实践范例**（小、内聚、config colocate） |

**重整建议**：作为其他 Feature 的对照样本；Phase R4 考虑目录 rename → `f17_virtual_player/` + shim。

#### F11 — 回合内增量 `features/f11_live_turn_sync/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `async_inject.py` | 207 | 后台 inject | ❌ 与 F02 handler 大量重复 |
| `task_state.py` | 143 | 异步任务状态 | ✅ |
| `delta.py` | 小 | 增量 payload | ⚠️ 依赖 F12 delta 构建 |
| `handler.py` | 小 | 启动后台 turn | ✅ |

**重整建议**：
- 提取 **`features/f02_player_turn/service.py`**（或 `shared/turn_pipeline.py`）作为 **唯一 inject 编排**；F02 handler 与 F11 async_inject 均调用它。
- `delta.py` 与 F12 共用 `f12/lib/delta_builder.py`（或提升为 `shared/world_delta/`）。

#### F12 — 世界 UI 同步 `features/f12_world_sync/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `formatter.py` | 238 | UI 格式化 | ⚠️ 依赖 F03 completion |
| `delta.py` | 266 | delta 构建 | ⚠️ 与 F11/F14 重叠 |
| `snapshot.py` | 中 | 全量快照 | ✅ |
| `handler.py` | 小 | HTTP | ✅ |
| `runner_bridge.py` | 小 | Runner 侧辅助 | ⚠️ 命名含糊 |

**重整建议**：
- 新建 `lib/delta_builder.py`、`lib/formatters.py`；F11/F14 只引用 lib。
- `runner_bridge.py` → `adapters/runner_snapshot.py`。
- Registry status 改为 `implemented`。

#### F13 — Loop 控制 `features/f13_world_loop_control/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `handler.py` | 小 | pause/resume | ✅ 但缺 `service.py`，被多处 deep import |

**重整建议**：pause/resume 逻辑进 `service.py`；`handler.py` 与 IPC 均委托 service。

#### F14 — 常驻 delta `features/f14_world_delta/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `handler.py` | 小 | poll + watcher | ✅ 定位正确（F03 的 world_loop 替代） |

**重整建议**：保持薄 handler；watcher 触发留在 F05，F14 只编排「读库 + delta」。

#### F15 — Prompt 追溯 `features/f15_prompt_trace/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| store / linker / refs / handler | 各 <180 | 分层清晰 | ✅ **范例** |

**重整建议**：维持；可选 `handler.py` 再薄一层委托 `service.py`。

#### F16 — WebSocket `features/f16_world_stream/`

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| handler + config | 小 | WS 推送 | ⚠️ 注册不在 http/ |

**重整建议**：业务留 f16；`http/ws.py` 负责 `register_world_stream_routes(app)`。

### 3.4 前端 Feature 内部审计

| 目录 | 文件数 | 问题 | 重整建议 |
|------|--------|------|----------|
| `world-stage/` | ~18，扁平 | 组件 + hook + lib 混放 | 拆 `components/`、`hooks/`、`lib/` |
| `game-loop/` | ~12 | 承载 F11/F13/F14/F16 前端逻辑 | 文档标注；可选拆 `world-sync/` 子 Feature |
| `main-chat/` | 1 组件 | 目录名误导 | 重命名 `player-input/` |
| `prompt-trace/` | 2 | 未进 FEATURE_REGISTRY | R0 补注册 |
| `features/index.ts` | — | F09e/F09f ID 与 endings/api 标注混乱 | 与后端 ID 对齐 |
| `store/` | 顶层 | 全局状态 | 保持（Robin Wieruch：store 可顶层） |
| 跨 feature import | — | 部分 deep import | R0 起 eslint `no-restricted-imports` |

---

## 四、目标架构与依赖规则

### 4.1 四层架构（延续 26，补充 integration 层）

```text
┌─────────────────────────────────────────────────────────────┐
│ L0 配置层                                                    │
│   hbm_scenario.yaml, turn_control.yaml, routing.yaml,        │
│   f08_virtual_player/config.yaml, config/manifest.yaml       │
├─────────────────────────────────────────────────────────────┤
│ L1 Runner 引擎层                                             │
│   core/runner/* + integration/*  （白名单 import L2）         │
├─────────────────────────────────────────────────────────────┤
│ L2 Demo 编排层                                               │
│   features/f01–f16, f08v  （handler → service → adapters）   │
├─────────────────────────────────────────────────────────────┤
│ L3 传输与展示层                                              │
│   http/* (REST + ws.py), web/src/*                           │
├─────────────────────────────────────────────────────────────┤
│ shared/  — 配置加载、错误、env_status、消息格式化（无业务规则）  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 依赖硬规则

| 规则 | 说明 |
|------|------|
| **D1** | L3 → L2 只允许 import Feature 的 `__init__.py` 或 `handler.py` |
| **D2** | L2 Feature 间：低 ID 不可 import 高 ID 编排（例：F05 不可 import F12 formatter） |
| **D3** | 跨 Feature 共享纯函数 → `shared/`；共享 delta 形状 → `shared/world_delta/` |
| **D4** | L1 仅 `core/runner/integration/*` 可 import F07/F08V/F15 |
| **D5** | 前端：`app → features → shared/api/store`，禁止 `shared → features` |
| **D6** | 每个 Feature PR 必须更新对应 Registry 行 + 验收步骤 |

### 4.3 Feature 编号终态

| ID | 名称 | 目录 |
|----|------|------|
| F08 | HTTP 传输 | `http/` |
| F08V → **F17**（推荐） | 虚拟玩家 | `f17_virtual_player/`（保留 `f08_virtual_player` shim 一周期） |

---

## 五、分阶段实施计划

> 每 Phase 独立 PR；合并前跑全量门禁。估算为单人日。

### Phase R0 — 文档与注册表（0.5d，低风险）

- [ ] 更新 `README.md`、`features/__init__.py`（F12=implemented，F05 modules 补全）
- [ ] 更新 `web/src/features/index.ts`（F11/F13–F16、prompt-trace、player-input 路径）
- [ ] 新增本文件（38）与 `hbm_demo/ARCHITECTURE.md`（可选一页纸）
- [ ] 明确 F08 vs F08V/F17 编号说明

**验收**：静态段 T1/T1g + `npm run build`。

### Phase R1 — 测试与脚本目录（1–2d，中风险）

- [ ] `scripts/tests/test_m0.py` + 按 Feature 拆分 acceptance
- [ ] `scripts/ops/` 放 start/stop/ports；根 scripts 保留 wrapper
- [ ] `scripts/test_m0_acceptance.py` 一行转发（CI 兼容）

**验收**：全量 E2E 与现网等价。

### Phase R2 — HTTP 层瘦身（2–3d，中高风险）

**R2a**
- [ ] `http/handlers/*.py` 或 routes 直引 Feature handler
- [ ] `game_service.py` 缩至 F01–F04/F06 兼容 export
- [ ] routes 内联 import（f07/f11/f13）迁入 handlers

**R2b**
- [ ] 新建 `http/ws.py`，F16 注册从 `agent_world/app/__init__.py` 迁入

**验收**：E2E T4 + F16 WS 段。

### Phase R3 — Runner integration 桥（3–5d，高风险）

- [ ] 新建 `core/runner/integration/{abcs,virtual_player,prompt_trace,story_advance}.py`
- [ ] `world_step.py` / `world_loop.py` / `hbm_agent.py` 仅调用 integration
- [ ] 新增 `test_integration_abcs.py`（不 boot 全 Runner）

**验收**：F07 全段 + Tier B E2E。

### Phase R4 — Feature 内部首批重构（3–4d，中风险）

按优先级：

1. **F02 + F11**：提取 `turn_pipeline` / `service.py`，消除 async_inject 重复
2. **F03 + shared**：迁出 `format_messages`；API2/F14 关系文档化
3. **F07**：拆 `conversation_control.py` → `conversation/*`
4. **F05 watcher**：去 F12 formatter 依赖
5. **前端**：`main-chat` → `player-input`；`world-stage` 分子目录

**验收**：相关 Feature 单测 + 全量门禁。

### Phase R5 — 深度收紧（可选，多 PR）

- [ ] F06 `world_db.py` 拆 queries
- [ ] F05 `routing.py` 按 Phase 拆文件
- [ ] F08V → F17 rename + shim
- [ ] `config/manifest.yaml`
- [ ] 删除 `check_turn4_bad_end`、`_legacy_inject_batch`（需改测试）
- [ ] 前端 eslint import boundaries

---

## 六、重整后完整文件树

> 含 `[新建]` `[移动]` `[重命名]` 标记；不含 `node_modules/`、`dist/`、`sim/`、`__pycache__/`。

```text
agent_world/hbm_demo/
│
├── README.md                              [更新]
├── ARCHITECTURE.md                        [新建]
├── __init__.py
├── .env / .env.example
├── hbm_scenario.yaml
│
├── run_hbm.py                             [保留 shim]
├── routes.py                              [保留 shim]
├── game_service.py                        [瘦身 ~60 行]
│
├── config/                                [新建]
│   ├── README.md
│   └── manifest.yaml
│
├── shared/
│   ├── __init__.py
│   ├── config_loader.py
│   ├── env_status.py
│   ├── errors.py
│   ├── settings.py
│   ├── messages.py                        [新建] 自 f03 format_messages
│   └── world_delta/                       [新建/可选]
│       ├── __init__.py
│       └── builder.py
│
├── core/
│   └── runner/
│       ├── __init__.py
│       ├── run_hbm.py
│       ├── kernel.py
│       ├── seed.py
│       ├── hbm_agent.py
│       ├── hbm_dispatcher.py
│       ├── world_step.py                  [重构]
│       ├── world_loop.py
│       ├── player_input_queue.py
│       ├── ipc_handlers.py
│       ├── broadcast_helper.py
│       └── integration/                   [新建]
│           ├── __init__.py
│           ├── abcs.py
│           ├── virtual_player.py
│           ├── prompt_trace.py
│           └── story_advance.py
│
├── features/
│   ├── __init__.py                        [更新 FEATURE_REGISTRY]
│   │
│   ├── f01_session/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── service.py                     [新建]
│   │   ├── lifecycle.py
│   │   ├── reset.py                       [Flask adapter]
│   │   ├── world_reset.py                 [Runner adapter]
│   │   ├── paths.py
│   │   ├── constants.py
│   │   ├── logging.py
│   │   └── adapters/
│   │       └── async_state.py             [新建] F11 清理封装
│   │
│   ├── f02_player_turn/
│   │   ├── __init__.py
│   │   ├── handler.py                     [瘦身 ≤80 行]
│   │   ├── service.py                     [新建] turn 编排
│   │   ├── inject.py
│   │   ├── task.py
│   │   └── adapters/
│   │       └── ipc.py                     [新建]
│   │
│   ├── f03_action_result/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── completion.py                  [仅完成判定]
│   │   └── adapters/
│   │       └── world_loop.py              [新建] F14 委托层
│   │
│   ├── f04_stats/
│   │   ├── __init__.py
│   │   ├── scoring.py
│   │   ├── deltas.py
│   │   └── service.py                     [可选]
│   │
│   ├── f05_story_routing/
│   │   ├── __init__.py
│   │   ├── routing.py
│   │   ├── routing.yaml
│   │   ├── routing_config.py
│   │   ├── agent_signals.py
│   │   ├── story_signals.py
│   │   ├── watcher.py                     [去 F12 依赖]
│   │   └── routing_phases.py              [可选拆分]
│   │
│   ├── f06_read_model/
│   │   ├── __init__.py
│   │   ├── world_db.py                    [Facade]
│   │   ├── display_names.py               [新建]
│   │   └── queries/                       [新建]
│   │       ├── messages.py
│   │       ├── moves.py
│   │       ├── rdc.py
│   │       └── grp.py
│   │
│   ├── f07_agent_control/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── turn_control.yaml
│   │   ├── runtime/
│   │   │   ├── turn_context.py
│   │   │   ├── pick_active.py
│   │   │   ├── inject_batch.py
│   │   │   ├── session_mirror.py
│   │   │   ├── player_response.py
│   │   │   └── player_facing_f2f.py
│   │   ├── conversation/
│   │   │   ├── control.py
│   │   │   ├── f2f_rules.py
│   │   │   └── batch_rules.py
│   │   ├── knowledge/
│   │   │   ├── builder.py
│   │   │   └── llm_params.py
│   │   └── story_knowledge/
│   │       ├── turn_hints.yaml
│   │       ├── agents/agent_{1..7}.yaml
│   │       └── shared/phase_{1..4}.yaml, plain_language.yaml
│   │
│   ├── f08_virtual_player/                [或 f17 + shim]
│   │   ├── __init__.py
│   │   ├── config.yaml
│   │   ├── config.py
│   │   ├── phase_places.yaml
│   │   ├── player_entity.py
│   │   └── player_f2f.py
│   │
│   ├── f11_live_turn_sync/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── async_inject.py                [调用 f02 service]
│   │   ├── task_state.py
│   │   └── delta.py
│   │
│   ├── f12_world_sync/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   ├── snapshot.py
│   │   ├── constants.py
│   │   ├── lib/
│   │   │   ├── delta_builder.py           [新建]
│   │   │   └── formatters.py              [新建]
│   │   └── adapters/
│   │       └── runner_snapshot.py           [原 runner_bridge]
│   │
│   ├── f13_world_loop_control/
│   │   ├── __init__.py
│   │   ├── handler.py
│   │   └── service.py                     [新建]
│   │
│   ├── f14_world_delta/
│   │   ├── __init__.py
│   │   └── handler.py
│   │
│   ├── f15_prompt_trace/
│   │   ├── __init__.py
│   │   ├── store.py
│   │   ├── linker.py
│   │   ├── refs.py
│   │   └── handler.py
│   │
│   └── f16_world_stream/
│       ├── __init__.py
│       ├── handler.py
│       └── config.py
│
├── http/
│   ├── __init__.py
│   ├── routes.py                          [薄路由]
│   ├── ws.py                              [新建 F16 注册]
│   ├── ipc_helper.py
│   ├── health.py
│   ├── http_errors.py
│   └── handlers/                          [可选]
│       ├── session.py
│       ├── player_turn.py
│       ├── world.py
│       └── prompt_trace.py
│
├── scripts/
│   ├── ops/
│   │   ├── start_demo.sh
│   │   ├── stop_demo.sh
│   │   └── demo_ports.sh
│   ├── tests/
│   │   ├── test_m0.py
│   │   ├── run_tests.sh
│   │   └── acceptance/
│   │       ├── f12_phase1.py
│   │       ├── f12_world_delta.py
│   │       ├── f12_visibility.py
│   │       ├── phase4_smoke.py
│   │       ├── test_f02_turn.py           [拆分]
│   │       ├── test_f07_abcs.py           [拆分]
│   │       └── test_e2e_http.py           [拆分]
│   ├── docs/
│   │   └── player_playthrough.md
│   ├── start_demo.sh                      [wrapper]
│   ├── stop_demo.sh                       [wrapper]
│   └── test_m0_acceptance.py              [shim 转发]
│
├── sim/                                   [gitignore 运行时]
│   └── hbm_memory_war/
│
└── web/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig*.json
    ├── eslint.config.js                   [更新 import 规则]
    ├── index.html
    ├── scripts/
    │   └── process_story_avatars.py
    ├── public/
    │   └── assets/story/
    │       ├── avatars/
    │       └── places/
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/
        │   ├── client.ts
        │   ├── config.ts
        │   ├── errors.ts
        │   ├── hbm.ts
        │   └── types.ts
        ├── constants/
        ├── store/
        ├── utils/
        ├── styles/
        │   └── global.css
        └── features/
            ├── index.ts                   [完整 REGISTRY]
            ├── boot/
            ├── game-loop/                   [F09b + F11/F13/F14/F16 FE]
            ├── layout/
            ├── player-input/                [重命名自 main-chat]
            │   ├── PlayerInput.tsx
            │   └── index.ts
            ├── world-stage/
            │   ├── index.ts
            │   ├── components/
            │   │   ├── WorldStage.tsx
            │   │   ├── RoomGrid.tsx
            │   │   ├── RoomCell.tsx
            │   │   ├── AgentCircle.tsx
            │   │   ├── AgentEphemeralBubble.tsx
            │   │   ├── AgentPhoneModal.tsx
            │   │   ├── AgentThreadDetail.tsx
            │   │   ├── AgentContactList.tsx
            │   │   ├── MessageThreadList.tsx
            │   │   ├── RoomHistoryModal.tsx
            │   │   ├── WorldEventModal.tsx
            │   │   ├── InnerOsTimeline.tsx
            │   │   ├── LocationHistoryTimeline.tsx
            │   │   └── RdcConnectionOverlay.tsx
            │   ├── hooks/
            │   │   └── useRoomEphemeralSpeeches.ts
            │   └── lib/
            │       ├── agentCircleLayout.ts
            │       ├── agentContactThreads.ts
            │       └── resolveSpeakerAgentId.ts
            ├── prompt-trace/
            ├── story-mode/
            ├── endings/
            └── shared/
                └── MessageBubble.tsx
```

**规模**：Python ~120 文件 + 前端 TS/TSX ~80 文件 + 配置/资产 ~30 文件 ≈ **230 源文件**（与现网相当，以搬家与拆分为主）。

---

## 七、Feature 对照表（重整后终态）

| ID | 名称 | 后端 | 前端 | 传输 |
|----|------|------|------|------|
| F00 | Runner | `core/runner/` | — | IPC |
| F01 | 会话 | `f01_session/` | — | `/session/*` |
| F02 | 玩家回合 | `f02_player_turn/` | `player-input/` | `/player-turn` |
| F03 | 动作结果 | `f03_action_result/` | — | `/action-result` |
| F04 | 数值 | `f04_stats/` | StatusPanel | — |
| F05 | 路由 | `f05_story_routing/` | — | 经 F14 watcher |
| F06 | 只读 DB | `f06_read_model/` | — | — |
| F07 | ABCS | `f07_agent_control/` | — | integration |
| F08 | HTTP | `http/` | `api/` | Blueprint |
| F17 | 虚拟玩家 | `f17_virtual_player/` | — | F2F |
| F09 | 前端壳 | — | `features/*` | — |
| F10 | 运维 | `scripts/ops/` | — | — |
| F11 | 回合同步 | `f11_live_turn_sync/` | `game-loop/` | — |
| F12 | 世界视图 | `f12_world_sync/` | `world-stage/` | `/world-snapshot` |
| F13 | Loop 控制 | `f13_world_loop_control/` | `game-loop/` | `/world-loop/*` |
| F14 | Delta | `f14_world_delta/` | `game-loop/` | `/world-delta` |
| F15 | Prompt | `f15_prompt_trace/` | `prompt-trace/` | `/prompt-trace/*` |
| F16 | WS | `f16_world_stream/` + `http/ws.py` | `game-loop/` | WebSocket |
| Story | 剧情模式 | — | `story-mode/` | — |

---

## 八、验收与门禁

### 8.1 每 PR 必跑

```bash
python agent_world/hbm_demo/scripts/test_m0_acceptance.py
cd agent_world/hbm_demo/web && npm run build
```

### 8.2 Phase 完成标准

| Phase | 额外标准 |
|-------|----------|
| R0 | Registry 与 README 一致；无代码行为变更 |
| R1 | 测试入口双路径（新 + shim）均绿 |
| R2 | routes 不再 `import game_service as gs` 拉 F12–F15 |
| R3 | `core/runner/*.py` 无直接 `features.f07` import（仅 integration） |
| R4 | F02 handler <100 行；F11 与 F02 无重复编排块 |
| R5 | F06 world_db facade 行数 <200 |

### 8.3 不破坏项

- 四节点试玩：Turn 4 / 12 / 16 / 25
- 对外 Python entry：`run_hbm.py`、`routes.hbm_bp`
- HTTP 路径前缀与响应形状（可 additive 字段）
- `sim/` 不入库

---

## 九、风险与回滚

| 风险 | 缓解 |
|------|------|
| R3 integration 抽层引入 tick 回归 | 先复制后删；Tier B E2E + phase4_smoke |
| F02/F11 合并 pipeline 破坏异步 | 保留 task_state 不变；只抽共有步骤 |
| 前端 world-stage 搬家 import 断裂 | 单 PR 内改 index.ts；build 门禁 |
| F17 rename 破坏 import | shim `f08_virtual_player` 重 export 一周期 |

每个 Phase 在 `hbm-demo-restructure` 上独立 commit；问题 revert 单 PR 即可。

---

## 十、与 37 / 26 的衔接

| 文档 | 关系 |
|------|------|
| **37** | 已完成：删 dead code、F15 reset 修复 |
| **26** | Feature 清单与四层定义；38 在其上补 **Feature 内部规范 + 分 Phase 迁移** |
| **37 §七 后续可选** | 已纳入 38 的 R1（test 拆分）、R5（check_turn4_bad_end） |

---

## 十一、参考资料

- Flask Blueprint / Application Factory：[Reintech](https://reintech.io/blog/flask-blueprint-patterns-large-applications)、[Miguel Grinberg Part XV](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xv-a-better-application-structure)
- Service / Repository 分层：[Leapcell — Deflating Fat Routes](https://leapcell.io/blog/deflating-flask-fat-routes-a-guide-to-service-and-repository-layers)
- React Feature 目录：[Robin Wieruch 2026](https://www.robinwieruch.de/react-folder-structure/)、[Modular Feature Design](https://www.codewithseb.com/blog/modular-feature-design-react-plug-and-play)
- Feature-Sliced public API：[DEV — eslint import boundaries](https://dev.to/vavilov2212/enforce-module-imports-in-fsd-using-eslint-plugin-import-2d72)
- 项目内：[`26_HBM_Demo_Feature规划与代码结构重整方案.md`](./26_HBM_Demo_Feature规划与代码结构重整方案.md)、[`37_HBM_Demo_代码重整与清理记录.md`](./37_HBM_Demo_代码重整与清理记录.md)

---

**下一步建议**：从 **Phase R0**（纯文档与 Registry）开工，零运行风险；随后 **R1 + R2a** 并行收益最大。
