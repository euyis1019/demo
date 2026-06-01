# HBM Demo 开发规范（务必遵守）

本文件是 `agent_world/drama_demo/` 子树的开发铁律。改动本目录代码前先读这里。
总览见 [README.md](README.md)，架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 1. 分层架构与依赖方向（D1–D5，不可违反）

四层：**L0 配置**（`config/prompts/`、`config/stories/`）· **L1 Runner**（`core/runner/`）·
**L2 Feature**（`features/fNN_*`）· **L3 传输/UI**（`http/` + `web/`），加跨层 `shared/`。

- **D1** L3 只经 Feature 的 `__init__.py`/`handler.py` 公共 API 调 L2，**禁止深引**内部文件。
- **D2** Feature 之间只经对方公共出口互相调用，不深引内部模块。
- **D3** `shared/` 不得 import `features/`（只放无业务的通用工具）。
- **D4** L1 Runner 访问 L2，**只能经 `core/runner/integration/` 白名单桥接**，不得直引 feature 内部。
- **D5** L0 是纯数据（YAML/参考图），不含逻辑；路径统一经 `shared/prompt_paths.py` 解析。

新增依赖前先问：方向对不对？要不要走桥接/公共出口？拿不准就先查 ARCHITECTURE.md 的依赖表。

## 2. 解耦原则

- **Facade 优先**：拆分大模块时保持对外 API 不变（facade + 内部 mixin/子模块），调用方零改动。
  参照 `f06 world_db`（queries/ mixin + facade）、`f07 conversation`（四个内聚模块）。
- **单一职责**：一个文件一件事。Python 文件 ~>400 行、前端组件 ~>300 行即应考虑按域拆分。
- **L1↔L2 唯一桥**：跨 Runner 与 Feature 的调用一律走 `core/runner/integration/`，新增交互在白名单里登记。
- **配置外置**：Agent 行为/剧情/路由/虚拟玩家配置只放 `config/prompts/`、`config/stories/`，
  **不要把 YAML 散回 feature 根目录**。
- **前端边界**：`app → features → shared(api/store/utils)`；`store` 不依赖 `features`；
  跨 feature 只从对方 `index.ts` 导入。eslint `no-restricted-imports` 会拦深引，**别绕过规则**。

## 3. 目录与命名

- Feature 用 `fNN_语义名` 编号目录；新 feature 取下一个空号，建对应公共出口 `__init__.py`。
- 每个有意义的模块都要有 README，含**文件职责表**（一行一文件）。改了文件作用就同步更新表。
- 设计/规划/方案类长文档放 **`dev_logs/`**，用 `NN_DRAMA_Demo_标题.md` 递增编号（当前最大见目录）。

## 4. 分支与提交

- **完整 feature 开分支**：从当前工作分支拉 `feature-语义名`，**开发完成、门禁绿了再合并**，不在主干上长期堆改动。
- 一个逻辑改动一个 commit，**小步可回归**（tracer bullet：先打通最薄一条竖切，再逐步加厚）。
- Commit message 用 conventional 前缀（`feat`/`fix`/`refactor`/`docs`/`chore`/`tune`），
  scope 标 `drama_demo` 或更细（`drama_demo/web`、`drama_demo/f07`），正文用中文说清「为什么」。
- 提交收尾加：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 只在用户要求时提交/推送；推送前确认在 feature 分支而非误推主干。

## 5. 测试与验收门禁（提交前必过）

- 每次改动后：`python3 scripts/test_m0_acceptance.py`（门禁，自动起停 Runner/Flask）
  **+** `cd web && npm run build`。两者全绿才提交。
- 纯新增、未被现存代码引用的模块（如 Story Pack 数据层初版），现存 E2E 门禁不可能因其变红；
  此类竖切**至少**跑该模块的专项单测 + import 冒烟，并诚实标注 E2E 门禁的运行状态（环境缺 key/网络时如实说明）。
- 门禁失败先判**是不是 LLM flake**（重跑一次确认），是真错再修；不要把 flake 当通过。
- E2E **只用隔离目录 `sim/_m0_e2e/`**，绝不碰用户试玩库 `sim/hbm_memory_war/`。
- 拆分/重构后用 import 冒烟 + 产物 diff（如 CSS bundle 字节对比）验证 facade 未破。

## 6. 安全红线（不可逾越）

- **用户试玩库 `sim/hbm_memory_war/` 只读**，开发/测试不得写它。
- **`sim/_m0_e2e/` 与 `sim/hbm_memory_war/` 严格隔离**，E2E 不外溢。
- **设计期生成工具（story_studio）只写 `config/stories/<id>/`，绝不写 `sim/`**（玩家存档）；
  隔离须机制级保证（import 图红线 + 输出路径断言），不靠自觉。
- `env_status.json` 等被高频读写的状态文件**必须原子写**（tempfile + `os.replace`），避免读到半截。
- 数据库读路径按只读约定加固，不在读路径做写操作。
- 删除"先前/废弃"代码或文件前先核对它是否真无引用（grep + 门禁），破坏性操作先确认。

## 7. 文档同步

- 改了模块结构/文件职责 → 同步对应 README 的文件职责表与 [README.md](README.md) 目录树。
- 重大设计决策落 `dev_logs/`；与代码不一致的旧文档要么改对要么删。
- 报告给用户**一律用中文**。

## 8. 当前进行中的 feature

- 分支 `story-framework-revamp`：**剧情数据驱动化**——把写死在代码里的 HBM 剧情（`features/f05_story_routing`
  的 if 链/常量、`drama_scenario.yaml`）抽成可外置的 **Story Pack**（`config/stories/<id>/`），
  使「只改 config 就能换一个完全不同的故事」，并补一套**设计期生成工具**（管理 agent 工作室 + validate 闸门），
  让用户只写一份剧情 brief 即可由 agent 生成整包 Story Pack。
  - 设计与规划见 dev_logs/40–46：40 解耦地图、41 参考 AI4VisualNovel、42 完整修改规划（§3 Story Pack schema、
    §4 解释器、§9 补全、§9.3 涌现社交存活性）、43 管理 vs 演员、44 端到端流程、45 设计期生成工具分阶段、
    46 完备性补充（42 条缺口）。
  - 落地铁律（dev_logs/45 §6）：**先有干净的 Story Pack 格式 + 解释器，再做生成工具**；
    G0 先把现有 HBM 抽成第一个手写参考包 `config/stories/hbm_memory_war/` 作回归锚点。
  - 分层落点：Story Pack 数据模型 + `StoryGraph.validate`（纯数据/算法，无业务）→ `shared/story_pack/`；
    故事解释器（信号→转移的表驱动调度）→ `features/f05_story_routing/`；运行期加载/播种经 L1 入口。
  - 本分支**不做** AIGC 实时出图（那是 `aigc-realtime-render` 分支）；静态剧情资源走设计期 Artist 步骤（tapnow）。
