# tools/story_studio — 设计期 Story Pack 生成工具（离线）

把一份 story **brief** 编译成整包 **Story Pack**（`config/stories/<id>/`）的离线 CLI。
是「编译器」，运行期解释器（`features/f05` + `shared/story_pack`）是「虚拟机」。设计见 dev_logs/45。

## 硬边界（红线，机制级保证，CLAUDE.md §6 / dev_logs/45 §1.2）

- **绝不进 Flask/Runner**：不 import `core.runner.kernel`/`seed`、`persistence.world_db`、`http.*`。
  由 `scripts/tests/test_story_studio.py` 的 import 图红线测试强制。
- **绝不写 sim/**（玩家存档）或包源码目录：所有写盘过 `safety.assert_safe_target`。
- 产出物 = `config/stories/<id>/` 整包数据，无任何 Python 控制流。

## 文件职责表（G1 契约 + 骨架）

| 文件 | 职责 |
|------|------|
| `__init__.py` | 公共出口 |
| `safety.py` | `assert_safe_target` 红线——只允许 config/stories/ 与包外 tmp，拒绝 sim/包源码 |
| `brief_schema.py` | 用户输入契约（semi-structured story brief 的 JSON Schema + `validate_brief`）|
| `authoring_schemas.py` | 生成期中间产物契约（`DESIGNER_OUTPUT_SCHEMA` + 通用 `validate_against`）|
| `base_agent.py` | 管理 agent 基类：`call_json_with_schema`（LLM 注入，生成→校验→重试→raise）|
| `writer.py` | sections(dict) → `config/stories/<id>/*.yaml` 落盘（过红线，幂等）|
| `orchestrator.py` | 编排器：Designer→Casting→Writer→assemble→validate→Critic 质量回路；尾部跑管理 agent 附加产物（onboarding / acting_guide），`_patch_meta` 写回 meta.yaml |
| `onboarding.py` | 管理 agent：按 brief/角色生成新手引导（背景+可做的行为）→ `meta.onboarding` |
| `acting_guide.py` | 管理 agent：按本故事基调生成统一「表演须知」（怎么演：口吻/show-don't-tell/潜台词/接玩家/沉默纪律/留在角色）→ `meta.acting_guide`，运行期 knowledge.py 只注入不内嵌规则 |
| `cli.py` | `validate-brief` / `compile` / `generate`(G2 占位) |

## 进度

- **G1（本切片）**：契约 + 落盘/校验骨架 + 安全红线。`generate`（brief→管理 agent 工作室→整包）
  与真实 LLM 流水线（Designer/Casting/Writer/Producer/Artist）在 **G2/G3** 接入。
- LLM 客户端在 `base_agent` 里**注入**，故全部逻辑可离线单测（fake client）。
