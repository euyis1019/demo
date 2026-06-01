# L2 — 业务编排 Features (`features/f01–f17`)

每个 `fXX_*` 是一个业务域包，对外只暴露 `__init__.py` 的公共 API。注册表见
`features/__init__.py` 的 `FEATURE_REGISTRY`。依赖规则见 [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
（D1/D2/D3）。

> 编号坑：**F08 = HTTP 传输（在 `http/`，不在此目录）**；虚拟玩家 canonical 是 **F17**
> （旧 `f08_virtual_player/` shim 已删除）。

---

## F01 — 会话与重开 `f01_session/`
管理 Flask 会话生命周期、路径、env 状态、世界重开。

| 文件 | 作用 |
|------|------|
| `models.py` | `DramaSession` dataclass（task_id/start_tick/place_id/phase/player_turn/stats/ending_id…）+ to/from dict |
| `lifecycle.py` | `create/save/load/get_or_create_session`、`save_session` |
| `paths.py` | `get_sim_dir/get_world_db_path/get_scenario/get_name_map` |
| `constants.py` | DEFAULT_SIM_ID、SESSION/TASKS key、初始 stats |
| `reset.py` | Flask 侧 reset（清 session + F11 async_state） |
| `world_reset.py` | Runner 侧 `reset_world_runtime()`、`purge_prompt_traces()`（经 integration.session 被 L1 调用） |
| `logging.py` | `log_turn_event()` 结构化回合事件日志 |

## F02 — 玩家回合 API1 `f02_player_turn/`
接收玩家台词，打分→路由→注入。

| 文件 | 作用 |
|------|------|
| `handler.py` | HTTP 入口 `handle_player_turn`；`_handle_v2_player_turn`（world loop）、`_handle_sync_inject`（Turn 25 同步）、`run_debug_inject` |
| `turn_pipeline.py` | **F02/F11 共用编排**：`prepare_turn`（打分+bad-end 门+构建 inject 事件）、`execute_inject`（IPC enqueue/batch）、`apply_routing_side_effects` |
| `inject.py` | `build_inject_events`、`check_turn4_bad_end`、`BAD_END_PUBLIC_MESSAGES` |
| `task.py` | `PendingTask` 模型 + inject 状态常量 + save_task |

## F03 — 动作结果 API2 `f03_action_result/`
轮询本回合完成；world loop 开启时整段委托 F14。

| 文件 | 作用 |
|------|------|
| `handler.py` | `get_action_result`：world_loop→委托 F14；否则读 F11 task_state 构建 delta |
| `completion.py` | `check_action_complete`、`effective_tick_for_task`、Phase 完成判定（如 Phase 4 Jensen F2F） |

## F04 — 数值与打分 `f04_stats/`
| 文件 | 作用 |
|------|------|
| `scoring.py` | `score_player_turn`：LLM 对玩家台词四维（vision/execution/trust/burnout）打分，失败回退启发式 |
| `deltas.py` | `apply_stat_deltas`、`initial_stats` |

## F05 — 剧情路由 `f05_story_routing/`
Phase 节点 A/B/C/D、结局裁定、RoutingWatcher。

| 文件 | 作用 |
|------|------|
| `routing.py` | `inject_agent_ids_for_phase`、`build_inject_payload`、`apply_routing`（节点副作用：移动/换 Phase）、`classify_turn25_intent`、`resolve_turn25_ending`、`classify_phase4_conclusion`（LLM 判 Phase4 谈成） |
| `agent_signals.py` | 节点检测：`detect_node_a/b/c`、`detect_bad_end`、`detect_phase4_offer_ending`（offer_* 信号）、`phase4_deal_transcript`（新成交话术→转录给 LLM） |
| `story_signals.py` | `has_story_signal`/`normalize_story_signal`：读 `story_advance_log` 结构化信号 |
| `routing_config.py` | 加载 `routing.yaml`：`is_agent_driven`、各类关键词（approve/expel/escort/phase4_deal…）、`is_story_advance_enabled` |
| `watcher.py` | **RoutingWatcher**：F14 轮询时按 tick 推进扫库 → 驱动节点 / bad_end / Phase4 早结局 → 产出 `pending_game_over`、路由 world_events |

## F06 — 只读世界模型 `f06_read_model/`
Flask 侧只读 SQLite 访问（`mode=ro` + 锁重试）。

| 文件 | 作用 |
|------|------|
| `world_db.py` | `ReadOnlyWorldDB` facade（连接 + `_with_retry`）+ `make_readonly_db`；多继承 queries/ 的 Mixin |
| `queries/messages.py` | 消息查询 Mixin：F2F / RDC / GRP / broadcast / 存在性检查 |
| `queries/moves.py` | 位置与移动日志 Mixin |
| `queries/events.py` | 群组成员/事件、relation、agent_state_log、story_advance_log Mixin |
| `queries/trace.py` | LLM trace / trace link / place 属性 Mixin |
| `display_names.py` | `SYSTEM_SENDER_NAME`、`sender_display_name` |

## F07 — ABCS Agent 控制 `f07_agent_control/`
L3 选角硬门 + L4 故事知识 + L6 玩家优先 + 对话节奏（纯软引导，无 L5 硬封锁）。
Runner 经 `core/runner/integration/abcs.py` 调用本 Feature。

| 文件 | 作用 |
|------|------|
| `config.py` | 加载 `turn_control.yaml`：F07 开关、world loop、选角/被动采样、inject 窗口 |
| `pick_active.py` | L3 选角：每 tick 哪些 Agent 可发言（primary/passive/frozen + inject 窗口） |
| `turn_context.py` | `build_turn_context`、`extract_inject_agent_ids`、`format_inject_dialogue` |
| `knowledge.py` | `build_agent_knowledge`（L4 故事知识注入）、`build_thread_recap`、`build_notification_snippet` |
| `llm_params.py` | 按 Phase/turn 解析 LLM 温度/max_tokens（passive 变体） |
| `conversation/` | 对话节奏(soft pacing)：`control.py`(主入口 build_conversation_hints) · `f2f_rules.py`(RDC 必回/anti-spam/位置提示) · `batch_rules.py`(节点 A 推进/批准) · `queries.py`(只读查询/关键词工具) |
| `conversation_control.py` | 兼容 shim → re-export `conversation/` |
| `player_response.py` | L6 玩家优先指令、`format_opening_directive`、inject 渠道 |
| `player_facing_f2f.py` | 玩家朝向 F2F 落库（前台/1v1 等无共处 Agent 时） |
| `inject_batch.py` | `notify_non_inject_active_agents`（通知本回合非 inject 的活跃 Agent） |
| `session_mirror.py` | session 知识镜像（bootstrap/merge），供 Runner 侧 Agent 读取 |

## F11 — 回合内增量同步 `f11_live_turn_sync/`
| 文件 | 作用 |
|------|------|
| `handler.py` | `start_background_turn`：起守护线程跑后台回合 |
| `async_inject.py` | `run_background_turn`：经 `turn_pipeline.prepare_turn`/`execute_inject` 在请求线程外完成打分+注入+路由 |
| `task_state.py` | 异步任务/会话运行态持久化（runtime.json）：`save_task_runtime`、`load_task_resolved`、`clear_async_state`、`sync_runtime_state` |
| `delta.py` | `build_turn_delta`：F03 轮询用增量 |

## F12 — 世界 UI 同步 `f12_world_sync/`
把 world.db 格式化为前端世界视图（UI 中立，不依赖 F14 展示逻辑）。

| 文件 | 作用 |
|------|------|
| `handler.py` | `get_world_snapshot`、`build_session_world_delta` HTTP 入口 |
| `snapshot.py` | 全量快照（自 tick 0：agents/places/messages） |
| `delta.py` | 增量 delta 构建（自 since_tick） |
| `formatter.py` | 四房间 F2F / agent 消息 / 位置变化 / 状态变化 / 群组事件 / 广播 → UI 中立结构 |
| `constants.py` | `DRAMA_AGENT_IDS`、`DRAMA_ROOM_PLACES` |
| `runner_bridge.py` | Runner 侧快照辅助导出 |

## F13 — Loop 控制 `f13_world_loop_control/`
| 文件 | 作用 |
|------|------|
| `service.py` | `get_world_loop_status` / `pause_world_loop` / `resume_world_loop` / `resume_if_paused`（session/start 自动解暂停） |
| `handler.py` | 委托 service（薄） |

## F14 — 常驻 delta `f14_world_delta/`
| 文件 | 作用 |
|------|------|
| `handler.py` | `get_world_delta`：调 F05 `scan_routing_if_needed` → F12 delta → F15 富化 → 合并路由 world_events / game_over（world_loop 下即 F03 的替代） |

## F15 — Prompt 追溯 `f15_prompt_trace/`
| 文件 | 作用 |
|------|------|
| `handler.py` | `get_prompt_trace` / `by_ref` / `list_prompt_traces` |
| `store.py` | trace 持久化（runner 侧写 trace 表） |
| `linker.py` | `record_action_links`：把动作与 trace_id 关联 |
| `refs.py` | `enrich_world_delta`：给 delta 事件挂 prompt_trace ref |

## F16 — WebSocket 推送 `f16_world_stream/`
| 文件 | 作用 |
|------|------|
| `config.py` | `is_world_stream_enabled`、`world_stream_poll_interval`（读 turn_control.yaml） |
| `handler.py` | WebSocket world-stream 处理（推送 delta；注册在 `http/ws.py`） |

## F17 — 虚拟玩家 `f17_virtual_player/`（canonical）
玩家在 world.db 中表现为 **agent 0**（从不 tick LLM），支撑 F2F 串线与 Phase 移动。

| 文件 | 作用 |
|------|------|
| `config.py` | `load_f08_config`、`is_f08_enabled`、`player_agent_id`（读 `config/prompts/virtual_player/config.yaml`） |
| `player_entity.py` | agent 0 注册、`is_virtual_player_agent`、`sync_player_place_on_routing`（按节点换房间）、`target_place_for_phase` |
| `player_f2f.py` | `build_player_f2f_payload`/`apply_player_f2f_payload`：把玩家台词作为 agent 0 的 F2F 写入 |
