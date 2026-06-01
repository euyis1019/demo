# Drama Demo 架构

四层架构、依赖硬规则、运行时数据流。总览见 [`README.md`](README.md)。

## 一、四层 + 跨层工具

```text
┌────────────────────────────────────────────────────────────────────┐
│ L0 配置   config/prompts/*（Agent prompt/路由/虚拟玩家）、            │
│           config/stories/<id>/、config/manifest.yaml、.env              │
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
      tick 推进时扫库 → route_story → Bert 导演判玩家新发言是否命中某条上膛 bert
                      → 命中则注入 reaction / 上膛后续(反应链) / 结局 bert→game_over
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

## 五、剧情路由与结局（F05）— bert（条件→反应）

剧情结构是 **bert**（`shared/story_pack/bert.py`）：一条 bert = `trigger`(玩家条件) → `target`(NPC) + `reaction`(反应)，
经 `requires`/`arms` 串成反应链，`ending` 非空即结局。无任何写死的幕/节点/关键词/回合。

- **Bert 导演**（`f05/director.judge_bert_triggers`）：玩家有新发言时，LLM 读最近对话判哪条「上膛」bert 命中（抓意图，非关键词）。
- **route_story**（`f05/interpreter_routing.py`）：命中 → 把 reaction 注入 target 下一拍 prompt（`f07 knowledge.py` 读 `hbm.bert_reactions`）、
  按 arms/requires 上膛后续 bert；命中结局 bert → 写 `hbm.ending_id/ending_kind/ending_summary` 收场。
- **RoutingWatcher**（`f05/watcher.py`）在 F14 轮询时按 tick 扫库 → 调 route_story → 持久化 hbm（`fired_berts`/`last_judged_player_tick`/`bert_reactions`）+ 产出 game_over。
- 「只在玩家有新发言时判一次」（`last_judged_player_tick` 去重）保证一句话不连环击穿、节奏自然。

## 六、关键不变量

- `sim/hbm_memory_war/` 是用户试玩库；E2E 用隔离的 `sim/_m0_e2e/`，**绝不污染**前者。
- Flask 以 `mode=ro` **只读**打开 world.db；`start_demo.sh` 校验 world.db 已生成。
- `env_status.json` **原子写**（临时文件 + `os.replace`），避免读到写一半的文件而误报「Runner not ready」。
- 对外 Python 入口稳定：`run_drama.py`、`routes.drama_bp`；HTTP 路径前缀与响应形状保持。

## 七、验收门禁

```bash
python3 agent_world/drama_demo/scripts/tests/test_story_studio.py   # 离线管理 agent 流水线单测（生成优先）
cd agent_world/drama_demo/web && npm run build                      # 前端类型 + 打包
# 改了管理层生成：python3 agent_world/drama_demo/scripts/test_create_acceptance.py（真 LLM 端到端）
```

不破坏项：管理 agent 把一段 brief 生成成结构合法(X+B 校验)的可玩 bert 包、`sim/` 不入库。
