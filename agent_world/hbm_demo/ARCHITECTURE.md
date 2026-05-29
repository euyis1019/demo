# HBM Demo 架构

四层架构、依赖硬规则、运行时数据流。总览见 [`README.md`](README.md)。

## 一、四层 + 跨层工具

```text
┌────────────────────────────────────────────────────────────────────┐
│ L0 配置   config/prompts/*（Agent prompt/路由/虚拟玩家）、            │
│           hbm_scenario.yaml、config/manifest.yaml、.env              │
├────────────────────────────────────────────────────────────────────┤
│ L1 Runner core/runner/*  +  core/runner/integration/*（白名单桥）    │
│           写 world.db、推进 tick、Agent LLM、IPC、常驻 world loop      │
├────────────────────────────────────────────────────────────────────┤
│ L2 编排   features/f01–f17（handler → service → adapters）           │
│           回合规则、剧情路由、打分、世界同步、Agent 控制              │
├────────────────────────────────────────────────────────────────────┤
│ L3 传输/UI http/（REST + ws.py）、web/src/                            │
├────────────────────────────────────────────────────────────────────┤
│ shared/   config_loader · env_status · errors · settings ·          │
│           messages · prompt_paths · routing_events（无业务规则）      │
└────────────────────────────────────────────────────────────────────┘
```

## 二、依赖硬规则

| 规则 | 说明 |
|------|------|
| **D1** | L3 → L2 只经 Feature 的 `__init__.py` 公共 API 或 `handler.py` |
| **D2** | L2 Feature 间：低 ID 不依赖高 ID 的**展示格式化**（例：F05 不 import F12 formatter） |
| **D3** | 跨 Feature 共享纯函数 → `shared/`；共享事件形状 → `shared/routing_events.py` |
| **D4** | **L1 只能经 `core/runner/integration/*` 调用 L2**（F07/F17/F15/F05/F01）；`core/runner/` 非 integration 文件不得直接 `import features.*` |
| **D5** | 前端：`app → features → shared/api/store`；`shared` 不得 import `features`；跨 feature 经各自 `index.ts`（eslint `no-restricted-imports` 强制） |

`core/runner/integration/` 是 L1↔L2 的**唯一白名单桥**：`abcs`（F07）、`virtual_player`（F17）、
`prompt_trace`（F15）、`story_advance`（F05）、`session`（F01）。

## 三、运行时数据流（一个玩家回合）

```text
浏览器 POST /player-turn(台词)
  → http/routes.player_turn → game_service.handle_player_turn (F02)
    → prepare_turn(): F04 打分 + apply_stat_deltas + Turn4 bad-end 门 + 构建 inject 事件
    → world_loop 开启:
        _handle_v2_player_turn → 经 turn_pipeline.execute_inject:
          IPC send_enqueue_player_input(events, player_f2f=agent0) + push mirror
        Runner 在下个 tick 边界把玩家 F2F 注入、各 Agent LLM 推进
    → 返回 { accepted, stats_update, current_phase, player_turn }

浏览器轮询 GET /world-delta?since_tick=N  (F14；F03 在 world_loop 时整段委托 F14)
  → F05 RoutingWatcher.scan_routing_if_needed():
      tick 推进时扫库 → 检测节点 A/B/C(agent_signals) → apply_routing(移动/换 Phase)
                      → Phase 4: 检测「谈成」→ 早结局; Phase 1: bad_end 检测
  → F12 build_session_world_delta(): 读 F06 → 四房间 F2F / agent 消息 / 位置 / 世界事件
  → F15 enrich: 给 delta 事件挂 prompt_trace ref
  → 返回 { room_f2f, agent_messages, location_changes, world_events, game_over?, stats… }

前端 worldDeltaApply: 合并 delta → 回放气泡/移动/事件;game_over.status
  → "completed" 进 EndingScreen,"game_over" 进 GameOverScreen。
```

## 四、世界 tick 循环（引擎，L1 不可见于 Demo 但决定行为）

- **同地点内**：Agent 串行决策 → 同一 tick 内 A 的 F2F 对后面的 B 立即可见。
- **跨地点**：`asyncio.gather` 并行 → 一个房间的慢 LLM 不阻塞另一个房间。
- **全局动作**（MOVE/RDC/GRP）：lockstep，本 tick 发出、下一 tick 才可见。
- **常驻 world loop**（F13/world_loop.py）：~1 tick/s 背景推进，玩家输入入队、下个 tick 边界注入。

## 五、剧情路由与结局（F05）

- **agent_driven 模式**：节点由 Agent 对话**信号 + 关键词**触发（非写死回合），Stats 仅 UI 展示。
  - 节点 A（Phase 1→2）：前台简报 + Jensen 批准访客。
  - 节点 B（Phase 2→3）：Tech VP 正面评估，Jensen 回谈判室。
  - 节点 C（Phase 3→4）：Jensen 清场三家 CEO。
  - 节点 D（结局）：**Phase 4 谈成即结束**——`story_advance(offer_*)` 信号，或 Jensen
    新成交话术触发一次 LLM 裁定（`classify_phase4_conclusion`）；否则 Turn 25 由
    `classify_turn25_intent` + trust 阈值兜底。
- **RoutingWatcher**（`f05/watcher.py`）在 F14 轮询时扫库驱动以上节点 + 产出 game_over。
- 结构化信号 `story_advance(...)` 与关键词检测互为补充（Jensen 常只「说」不「调工具」，
  故关键词/LLM 兜底）。

## 六、关键不变量

- `sim/hbm_memory_war/` 是用户试玩库；E2E 用隔离的 `sim/_m0_e2e/`，**绝不污染**前者。
- Flask 以 `mode=ro` **只读**打开 world.db；`start_demo.sh` 校验 world.db 已生成。
- `env_status.json` **原子写**（临时文件 + `os.replace`），避免读到写一半的文件而误报「Runner not ready」。
- 对外 Python 入口稳定：`run_hbm.py`、`routes.hbm_bp`；HTTP 路径前缀与响应形状保持。

## 七、验收门禁

```bash
python3 agent_world/hbm_demo/scripts/test_m0_acceptance.py   # E2E + 静态契约
cd agent_world/hbm_demo/web && npm run build                 # 前端类型 + 打包
```

不破坏项：四节点试玩（节点 A/B/C/D）、三结局路径、`sim/` 不入库。
