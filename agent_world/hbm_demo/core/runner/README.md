# L1 — Runner (`core/runner/`)

HBM Demo 的 **Runner 层**：包装通用引擎 `agent_world/runner/`，seed 世界、跑 LLM 多
Agent 常驻 world loop、写 `sim/hbm_memory_war/world.db`、监听 IPC。

入口：`python -m agent_world.hbm_demo.run_hbm`（根 `run_hbm.py` 是转发 shim）。

## 依赖边界（D4）

`core/runner/` **只能经 `integration/` 白名单**调用 L2（features）。除 `integration/`
外的文件**不得**直接 `import agent_world.hbm_demo.features.*`。

## 文件职责

| 文件 | 作用 |
|------|------|
| `run_hbm.py` | 进程入口：解析 `--config/--sim-dir`、`build_kernel`、起 `WorldLoopOrchestrator` + IPCServer、wire IPC handlers、写 env_status（starting/running/stopped）。 |
| `kernel.py` | `build_kernel()`：加载 scenario、seed 世界、构造 world_db/world_state/clock/agents/world_step；`.env` 加载、`resolve_api_key`、`llm_request_extras`、place_mutation 钩子。 |
| `seed.py` | `seed_world()`：把 scenario 的地点/连接/Agent 写入 world.db（首次）。 |
| `hbm_agent.py` | HBM Agent：组装 system prompt（soul + story knowledge + thread recap + conversation hints）、调 LLM、产出动作；含 `story_advance` 工具定义（approve_visitor/expel_ceos/offer_join/offer_seed…）。 |
| `hbm_dispatcher.py` | HBM 动作分发：把 Agent 工具调用路由到引擎总线；静默忽略 `request_move` 等。 |
| `world_step.py` | 单 tick 编排（封装引擎 step）：选角(F07) → 感知 → Agent LLM → 分发 → F2F/玩家朝向落库。 |
| `world_loop.py` | `WorldLoopOrchestrator`：常驻 ~1tick/s 循环、玩家输入队列消费、session mirror、pause/resume、写 env_status。 |
| `player_input_queue.py` | 玩家输入 / 脚本事件入队结构（IPC enqueue → 下个 tick 边界注入）。 |
| `ipc_handlers.py` | 注册 IPC 命令处理：INJECT_BATCH / ENQUEUE_PLAYER_INPUT / MOVE / RESET_WORLD / LIST_PLACES 等；含 `_legacy_inject_batch`（world loop 关闭时的 v1 回退）。 |
| `broadcast_helper.py` | 广播类事件（如 Turn 16 彭博快讯）落库辅助。 |
| `integration/` | **L1↔L2 唯一白名单桥**（见下）。 |

## `integration/` 白名单桥

Runner 只通过这些模块触达 L2，使 L1 不直接耦合 Feature 内部实现：

| 模块 | 暴露 | 来源 Feature |
|------|------|--------------|
| `abcs.py` | turn_context / pick_active / knowledge / conversation hints / player-facing F2F / session mirror 等 | F07 |
| `virtual_player.py` | `build/apply_player_f2f_payload`、`is_f08_enabled`、`player_agent_id` | F17 |
| `prompt_trace.py` | `PromptTraceStore`、`record_action_links` | F15 |
| `story_advance.py` | `normalize_story_signal` | F05 |
| `session.py` | `get_name_map`、`reset_world_runtime`、`purge_prompt_traces` | F01 |

## Boot 流程（`run_hbm.main`）

```text
parse args → load_scenario → write_env_status(starting)
  → build_kernel(scenario, sim_dir)         # seed 世界、构造内核
  → WorldLoopOrchestrator(...)              # 常驻 loop（F07 配置决定是否启用）
  → IPCServer + wire_handlers(ipc_handlers) # 注册 L2 命令处理（经 integration）
  → write_env_status(running) → orchestrator.start() → ipc_server.run_forever()
  → 退出: flush、close、write_env_status(stopped)
```
