# 37 — HBM Demo 代码重整与清理记录

> 分支：`hbm-demo-restructure`（自 `jensen-hwang-demo` @ `44c7319` 拉出，非 main）  
> 日期：2026-05-23  
> 目标：删除已退役的 hardening / legacy 路径与孤儿 UI，不影响 Demo 运行与试玩体验。

---

## 一、分支与前置条件

| 项 | 说明 |
|----|------|
| 基线 | `jensen-hwang-demo`（demo 功能线） |
| 重整分支 | `hbm-demo-restructure` |
| 校验 | 与 demo 线同指向 `44c7319`；merge-base 与 main 为 Initial commit |

---

## 二、删除文件清单

### 2.1 前端孤儿 UI

| 路径 | 原因 |
|------|------|
| `web/src/features/main-chat/MainChat.tsx` | F12 世界舞台取代中栏聊天 |
| `web/src/features/main-chat/MessageBubble.tsx` | 迁至 `shared/MessageBubble.tsx` |
| `web/src/features/layout/ThreeColumnLayout.tsx` | 仅保留 `TwoColumnLayout` |
| `web/src/features/observer/ObserverPanel.tsx` | RDC/GRP 已并入 world-stage |
| `web/src/features/observer/index.ts` | 目录整体移除 |
| `web/src/features/observer/useEnvStatus.ts` | 迁至 `game-loop/useEnvStatus.ts` |

### 2.2 F07 experience_hardening 退役

| 路径 | 原因 |
|------|------|
| `features/f07_agent_control/batch_guard.py` | 仅 hardening 写入，从未读取 |

### 2.3 F05 legacy_stats 回滚路径

| 路径 | 变更 |
|------|------|
| `features/f05_story_routing/routing.py` | 删除 `_legacy_node_a/b/c_applies` 及双轨分支 |
| `features/f05_story_routing/routing_config.py` | 删除 `is_legacy_stats()`；默认 `agent_driven` |

### 2.4 独立 Synthetic 测试资产

| 路径 | 原因 |
|------|------|
| `scripts/acceptance/f12_synthetic.py` | 与主门禁 `test_m0_acceptance.py` 重复 |
| `scripts/fixtures/f12_synthetic_fixture.json` | 配套 fixture |
| `web/scripts/test_f12_synthetic_fixture.ts` | 配套前端回放脚本 |

---

## 三、代码修改摘要（非删除）

### 3.1 F07 配置与运行时

- `turn_control.yaml`：移除整块 `experience_hardening:` 配置
- `config.py`：移除 `is_experience_hardening`、`rdc_quota_for`、`first_f2f_required_agents` 等
- `completion.py`：移除 F2F 硬完成分支，保留 F07 Phase 1/4 + 通用超时
- `world_step.py`：移除 `BatchGuardState`、`_mark_rdc_if_sent`、`_resolve_batch_llm_params` hardening 分支
- `player_response.py` / `hbm_agent.py`：移除 hardening 专用 L6 / 行动规则
- `inject_batch.py`：删除 `notify_jensen_player_summary`
- `__init__.py`：不再 export `is_experience_hardening`
- `ipc_handlers.py`：RESET 时暂停 world loop、二次 purge F15 trace；重置后保持 paused 直至 enqueue
- `world_reset.py`：新增 `purge_prompt_traces()`；idle tick 不写 prompt trace（`player_inject_tick` 为空）
- `world_reset.py`：移除 `_batch_guard_state` 清理

### 3.2 前端整理

- `MessageBubble` → `features/shared/`
- `useEnvStatus` → `features/game-loop/`
- `App.tsx` 与 world-stage 组件更新 import
- `global.css`：移除 `.main-chat` / `.observer-panel` 死样式

### 3.3 测试与文档

- `scripts/test_m0_acceptance.py`：移除 hardening / legacy / synthetic 相关断言
- `README.md`：双栏 UI、F07 运行时、agent_driven 路由说明
- 本文件（dev_logs/37）

---

## 四、保留项（勿删）

- 根 shim：`run_hbm.py`、`routes.py`、`game_service.py`
- F01–F16 Feature 主体、`test_m0_acceptance.py` 主门禁
- `features/f07_agent_control/phase4_smoke.py`（可选 IPC 冒烟，测试仍引用）
- `web/scripts/test_world_sync.ts`（worldSync 单元测试）

---

## 五、验收

```bash
python agent_world/hbm_demo/scripts/test_m0_acceptance.py
cd agent_world/hbm_demo/web && npm run build
```

---

## 六、后续可选（未做）

- `phase4_smoke.py` 迁至 `scripts/acceptance/`
- `test_m0_acceptance.py` 按 Feature 拆分为多文件
- `web/README.md` 更新 F09 目录说明
