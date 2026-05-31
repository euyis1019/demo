# F08 / L3 — HTTP 传输 (`http/`)

Flask Blueprint (`hbm_bp`)：把浏览器请求委托给 L2 features，并提供 Flask 侧 IPC 客户端、
健康探针、WebSocket 注册、错误格式化。注册到 `agent_world.app`（根 `routes.py` 是
转发 shim → `http.routes.hbm_bp`）。

依赖规则：L3 只经 Feature 的 `__init__.py`/`handler.py` 公共 API 调 L2，不深引内部（D1）。

## 文件职责

| 文件 | 作用 |
|------|------|
| `routes.py` | `hbm_bp` Blueprint：所有 REST 端点（含大厅 `/lobby/*`），做参数解析 + 委托 L2 + 错误映射（薄路由） |
| `world_manager.py` | Flask 侧「大厅/世界生命周期」单例 `WORLD_MANAGER`：`list_stories`、`create_story`（后台线程异步跑 story_studio 生成整包 + 可选出图，用 job 跟踪）、`activate`（按故事起/重启 Runner 子进程并设为当前故事） |
| `ipc_helper.py` | **Flask 侧 IPC 客户端**：`get_ipc_client`、`send_inject_batch/enqueue_player_input/move_agent/reset_world`、`push_session_mirror`、`wait_for_loop_window`、`resolve_loop_min_ticks`；错误→`IpcFailedError/IpcTimeoutError` |
| `ws.py` | F16 WebSocket 注册：`register_world_stream_routes(app)`，推送 world-delta 流 |
| `health.py` | `check_stack_health`：Runner 就绪 + world.db 可读探针（兜底捕获异常） |
| `http_errors.py` | 把领域异常（RunnerNotReady/IpcFailed/DatabaseRead…）映射为 HTTP 状态 + JSON |
| `__init__.py` | Blueprint 装配入口 |

## REST 端点（前缀 `/api/hbm/simulations/<sim_id>/`）

| 方法 | 路径 | 委托 | 说明 |
|------|------|------|------|
| POST | `session/start` | F01 + F13 | 初始化 session、push mirror、必要时 `resume_if_paused` |
| POST | `session/reset` | F01 | IPC RESET_WORLD + session 清零 |
| GET | `session` | F01 | 当前 session 快照 |
| GET | `health` | F01/F06 | Runner + world.db 就绪（未就绪 503） |
| GET | `env-status` | shared.env_status | Runner tick / loop 状态 |
| POST | `player-turn` | **F02** | 打分 + 注入；返回 accepted/processing |
| GET | `action-result` | **F03**(→F14) | 轮询完成；world_loop 时同 world-delta |
| GET | `world-snapshot` | F12 | 全量世界快照（UI 校准） |
| GET | `world-delta?since_tick=` | **F14** | 增量同步（路由事件 / game_over 也在此） |
| GET/POST | `world-loop/status\|pause\|resume` | F13 | 常驻 loop 控制 |
| GET | `prompt-trace/<id>` · `prompt-trace/by-ref` · `prompt-traces` | F15 | Prompt Inspector |
| POST | `debug-inject` | F02 | 调试用手动 IPC inject |

## 大厅端点（前缀 `/api/hbm/lobby/`，不带 `<sim_id>`）

| 方法 | 路径 | 委托 | 说明 |
|------|------|------|------|
| GET | `lobby/stories` | WorldManager | 列出已有故事（story_id/title/有无图片素材/NPC 数） |
| POST | `lobby/stories` | WorldManager | 输入一段剧情 → 后台异步生成整包，返回 `job_id` |
| GET | `lobby/jobs/<job_id>` | WorldManager | 轮询生成进度（running/done/error + step） |
| POST | `lobby/activate` | WorldManager | 激活某故事（起 Runner、设为当前故事），返回 `{story_id, ready}` |

响应统一 `{"success": bool, "data": {...}}`；端点只校验 `sim_id` 并转发，不含业务编排
（loop 自动 resume 等已下沉 F13 service）。
