# F10 — 运维与验收 (`scripts/`)

启动/停止脚本与验收测试。

```text
scripts/
├── ops/                       # 运维脚本
│   ├── start_demo.sh          #   一行启动 Runner + Flask + Vite（校验 DMXAPI_KEY、
│   │                          #   等 Runner 就绪 + world.db 生成 + Flask health 200）
│   ├── stop_demo.sh           #   停止全部进程
│   └── demo_ports.sh          #   端口选择/探测辅助
├── tests/
│   ├── test_m0.py             #   验收主套件：静态契约 + F0x 单测 + 实时 E2E（自动起停
│   │                          #   Runner/Flask，用隔离的 sim/_m0_e2e/，绝不碰用户库）+ 前端构建
│   ├── run_tests.sh           #   测试封装
│   └── acceptance/            #   分项 acceptance：f12_phase1 / f12_world_delta /
│                              #   f12_visibility / phase4_smoke（Phase4 IPC 烟测）
├── docs/
├── start_demo.sh              # 兼容 wrapper → ops/start_demo.sh
├── stop_demo.sh              # 兼容 wrapper → ops/stop_demo.sh
└── test_m0_acceptance.py      # 门禁入口 shim → tests/test_m0.main()（CI 兼容）
```

## 常用命令（仓库根目录）

```bash
# 启动 / 停止
./agent_world/drama_demo/scripts/ops/start_demo.sh
./agent_world/drama_demo/scripts/ops/stop_demo.sh

# 验收门禁（自动起停 Runner/Flask，跑 E2E + 前端构建）
python3 agent_world/drama_demo/scripts/test_m0_acceptance.py
```

## 约定

- **E2E 用 `sim/_m0_e2e/`**，不污染用户试玩库 `sim/hbm_memory_war/`。
- 门禁退出码已传播（`sys.exit(main())`），失败即非 0。
- 提交前务必门禁全绿 + `cd web && npm run build` 通过。
- 实时 E2E 含 LLM 调用，需 `.env` 配 `DMXAPI_KEY`（否则降级 Tier A，跳过 LLM 断言）。
