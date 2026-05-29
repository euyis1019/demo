# HBM Demo 架构一页纸

> 结构重整依据：[`dev_logs/38_HBM_Demo_项目结构重整方案.md`](../../dev_logs/38_HBM_Demo_项目结构重整方案.md)

## 四层架构

```text
L0 配置     hbm_scenario.yaml, turn_control.yaml, routing.yaml, .env
L1 Runner   core/runner/          写 world.db、tick、Agent LLM、IPC
L2 编排     features/f01–f16      回合规则、路由、ABCS、世界同步
L3 传输/UI  http/, web/src/       Flask Blueprint + React 双栏 UI
shared/     跨层工具（config_loader, env_status, errors）
```

## 运行链路

```text
浏览器 → web/api/hbm.ts (+ WS)
      → Flask hbm_bp (http/routes.py)
      → features/* handler
      → IPC → Runner (core/runner/run_hbm)
      → sim/hbm_memory_war/world.db
```

## Feature 编号说明

| ID | 名称 | 目录 |
|----|------|------|
| F00 | Runner | `core/runner/` |
| F01–F06 | 会话/回合/结果/数值/路由/只读DB | `features/f01_*` … `f06_*` |
| F07 | ABCS Agent 控制 | `features/f07_agent_control/` |
| **F08** | **HTTP 传输** | `http/` |
| **F17** | **虚拟玩家**（canonical） | `features/f17_virtual_player/`（旧 `f08_virtual_player/` shim 已移除） |
| F09 | 前端 UI | `web/src/features/` |
| F10 | 运维脚本 | `scripts/ops/`、`scripts/tests/` |
| F11–F16 | 增量同步/世界视图/loop/delta/prompt/WS | `features/f11_*` … `f16_*` |

## 依赖规则（目标态）

- L3 → L2：经 handler 或 Feature `__init__.py` 公共 API
- L2 低 ID 不可依赖高 ID 的展示格式化（例：F05 不 import F12 formatter）
- L1 经 `core/runner/integration/` 白名单调用 F07/F17/F15（Phase R3）
- 前端：`app → features → shared/api/store`

## 入口与 shim

| 文件 | 用途 |
|------|------|
| `run_hbm.py` | `python -m agent_world.hbm_demo.run_hbm` |
| `routes.py` | `hbm_bp` Blueprint |
| `game_service.py` | 历史 re-export（逐步瘦身，见 Phase R2） |

## 验收

```bash
python agent_world/hbm_demo/scripts/test_m0_acceptance.py
cd agent_world/hbm_demo/web && npm run build
```
