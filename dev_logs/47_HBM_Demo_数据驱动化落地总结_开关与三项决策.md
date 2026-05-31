# HBM Demo 剧情数据驱动化 — 落地总结（开关清单 + 三项最终决策）

> 配套 dev_logs/40–46（设计/规划）。本篇记录**已实现**的落地状态、运行期开关、以及用户拍板的三项决策。
> 分支 `story-framework-revamp`。所有运行期改动**开关式**，默认关 → 旧行为字节不变；离线全测 + 完整 LLM E2E 已验证。

## 一、已落地（G0 运行期 + G1–G6 设计期生成工具）

| 模块 | 落点 | 说明 |
|------|------|------|
| Story Pack 数据层 + validate(V+X) | `shared/story_pack/` | 节点/边/结局 + 世界原语；结构 + 跨文件引用闭合校验 |
| 表驱动解释器 | `features/f05_story_routing/interpreter.py`(+`interpreter_routing.py`) | 读 Story Pack 做路由决策，离线逐态等价旧 if 链 |
| 运行期播种 | `core/runner/run_hbm.py` + `shared/story_pack/scenario_adapter.py` | 从 Story Pack 投影 scenario → build_kernel/seed |
| 通用验收 gate | `scripts/ops/validate_story_pack.py` + test_m0 | 对任意 Story Pack 校验，不写死 HBM 常量 |
| 设计期生成工具 | `tools/story_studio/` | brief→Designer→Casting→Writer→validate 自愈→完整包；review/局部重生/成本护栏/trace/素材清单 |

## 二、运行期开关（默认全关 → 旧行为不变）

| 环境变量 | 作用 | 默认 |
|----------|------|------|
| `HBM_STORY_PACK_SEED=1` | Runner 启动时从 Story Pack 播种世界 | 关（用 hbm_scenario.yaml）|
| `HBM_STORY_PACK_ROUTING=1` | watcher 用解释器驱动路由 | 关（用旧 if 链）|
| `HBM_FREE_MOVE=1` | 放开 agent 自主 request_move | 关（脚本搬人）|

> 实机验证：`HBM_STORY_PACK_SEED=1 HBM_STORY_PACK_ROUTING=1` 跑完整门禁 `ALL M0–M7 TESTS PASSED`；
> Runner 日志确认 `从 Story Pack 'hbm_memory_war' 播种世界` + agents/places 正确 + agent 真实 LLM 200。

## 三、三项最终决策（用户拍板）

### 决策1 — 美术资源：txt 清单，用户自备（不自动出图）
`tools/story_studio/asset_manifest.py` 从 Story Pack 推导封面/每地点背景/每 NPC 立绘，产
`ASSETS_TODO.txt`：每张给建议文件名/尺寸 + 详细文生图提示词（统一画风）。**不调任何出图模型**，
用户照单自备素材放进 `assets/`。CLI：`story_studio assets <id> --write`。

### 决策2 — 涌现社交（"玩家影响一个 agent 波及其他 agent"）：LLM 自发涌现，不加确定性 hook
**结论：无需任何引擎改动。** 这套机制本就位于通用引擎层：
- 初始关系网由 `relations.yaml` 播种进 `RelationGraph`（已验证 17 条边落库）；
- agent 人设（soul）驱动情绪化反应；
- 运行期 `relation_change` 工具 + `perception` 感知 + `segment` 记忆 自发驱动关系/情绪演化；
- 任何带"有意义关系网 + 情绪化人设"的 Story Pack 自动获得这套动态。

不保证"必然触发"（是 LLM 当拍涌现，非确定性因果），这是刻意选择。生成期 Casting agent 已被
引导去写交织的关系网 + 会因他人遭遇而反应的人设，提升涌现质量。

### 决策3 — agent 自由移动：放开 request_move，但强引导"非必要不移动"
`HBM_FREE_MOVE=1` 时 `HbmActionDispatcher` 不再吞 request_move，落到通用 dispatcher 真正生效；
同时 `hbm_agent` prompt 改为"可移动到相邻地点，但非必要不要移动，仅剧情需要时移动"，避免乱跑卡死。

## 四、玩家权限

玩家（agent 0）拥有全部交互权限：私信(RDC)/面对面(F2F)/群聊(GRP)/移动(MOVE)，记于
`meta.player.capabilities`，经虚拟玩家路径下发；CapabilityTable 播种与原 scenario 一致。

## 五、测试

离线 63 测试全绿（数据/校验/解释器逐态等价/播种 world.db 逐行等价/生成工具回路/自由移动门控）+
完整 LLM 实机 E2E（双开关 ON）通过。所有开关默认关，旧路径零改动。
