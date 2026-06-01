# 跨层工具 (`shared/`)

跨 Feature 的通用工具：配置加载、运行时状态、错误、设置、消息格式化、prompt 路径、
路由事件契约。**不含业务规则**，且 `shared/` 不得 import `features/`（D3/D5）。

| 文件 | 作用 |
|------|------|
| `config_loader.py` | `load_scenario()`：解析 `drama_scenario.yaml`（地点/Agent/LLM/群聊） |
| `prompt_paths.py` | L0 prompt 路径解析：`turn_control_path`、`routing_config_path`、`virtual_player_config_path`、`story_knowledge_dir`、`scenario_path` 等（统一指向 `config/prompts/`） |
| `env_status.py` | `env_status.json` 读写：`write_env_status`（**原子写**：临时文件 + `os.replace`）、`read_env_status`、`is_runner_ready`、`patch_ipc_server_env_status`、`normalize_env_status` |
| `settings.py` | 环境驱动常量：`DEFAULT_IPC_TIMEOUT`、`DEFAULT_MOVE_TIMEOUT`、`DEFAULT_RESET_TIMEOUT`、`DB_CONNECT_TIMEOUT`、`DB_READ_RETRIES` |
| `errors.py` | 领域异常：`RunnerNotReadyError`、`IpcFailedError`、`IpcTimeoutError`、`DatabaseReadError`、`WorldLoopDisabledError` |
| `messages.py` | 跨 Feature 的消息格式化辅助 |
| `routing_events.py` | F05↔F12 **解耦契约**：`format_routing_world_events`、`ROUTING_WORLD_EVENT_CONTENT`（节点 A/B/C 的世界事件文案）——让 F05 产出原始路由事件、F12/F14 消费而不互相 import |
| `active_game.py` | 运行期「当前在玩哪个故事」的可变状态：`get_active_story`/`set_active_story`（默认 canglan_sword，大厅选/建故事后由 WorldManager 切换）、`active_sim_dir`（当前故事的 sim 目录，优先级：已激活故事 > env `DRAMA_SIM_DIR` > 默认）——纯状态，不依赖 features（D3） |
| `story_config.py` | 活跃故事运行期配置门面（运行期数据驱动化）：`active_story_id`（委托 `active_game`，默认 canglan_sword，运行期可切）、`active_pack`、`clear_pack_cache`（切故事后清包缓存）、`initial_node_id`、`node_place`、`node_exists`、`node_inject_agents`、`node_beats_label`、`player_start_place`——纯读 `shared/story_pack`（D3），L1/L2 据此换故事即换游戏 |
| `__init__.py` | 统一再导出常用符号 |

> `env_status.json` 被 Runner 每 tick(~1s)重写、Flask 每次轮询读取；原子写避免读到
> 写一半的文件导致误报「Runner not ready」。详见 [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §六。
