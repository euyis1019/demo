# 技术设计 · AIGC 实时整帧渲染（分支 `aigc-realtime-render`）

把 game 的画面从**静态渲染**（React 组件 + 预制素材按 world-delta 数据拼场景）改为
**后端每 tick 用极速文生图模型实时生成整帧游戏画面**，前端只负责显示。

> 状态：设计稿（未动代码）。基线 `jensen-hwang-demo @ 4fdbf44`。

## 0. 已定路线

| 决策 | 选择 | 影响 |
|------|------|------|
| 生成内容 | **整帧游戏画面** | 前端退化为"看图"，世界舞台组件被替换 |
| 调用位置 | **后端生成** | 新增后端出图服务，经 world-delta/WS 下发 |
| 生成时机 | **每 tick 实时** | 出图进入 tick 主循环关键路径 |
| 静态渲染 | **完全替换** | 删 `world-stage` 渲染，换帧显示组件 |
| 模型 | **极速文生图**（Flux Schnell / SDXL-Turbo / LCM 类） | 单图 ~0.5–2s |
| 一致性 | **固定种子 + 参考图**（IP-Adapter/ControlNet） | 锁画风与布局 |
| 延迟兜底 | **降 tick 速率匹配出图** | tick 节奏由出图耗时驱动 |

## 1. 硬约束（必须先认清）

- **极速模型单图仍要 0.5–2s**，而当前 tick 默认 1s
  （`features/f07_agent_control/config.py:93` 读 `world_loop.tick_interval_sec`）。
  选了"降 tick 速率匹配" → **tick 不再是固定 1s，而是"出完上一帧才进下一 tick"**，
  整体节奏被出图耗时拖慢，这是已接受的取舍。
- **整帧每 tick 重生**天然会人物/场景闪变 → 用"固定种子 + 参考图"压制，但极速模型对
  ControlNet/IP-Adapter 的支持参差，**模型必须支持传 seed + reference image**，否则一致性无法保证（见 §9 风险）。
- 出整帧意味着**每帧都要把世界状态翻译成一段画面 prompt**，prompt 质量直接决定可玩性。

## 2. 总体数据流（改造后）

```
world_loop._loop()  (core/runner/world_loop.py:275)
  └─ run_one_tick()  推进世界状态(谁说话/移动/phase)
       └─ [新] SceneRenderService.render(tick, world_state)
            1. 读当前世界状态 → 组装画面 prompt（房间/在场人物/正在发言/phase/近期事件）
            2. 调极速文生图(固定 seed + 该场景参考图)
            3. 落盘 sim_dir/frames/<tick>.png + 写 frame 表
       └─ tick 间隔 = max(min_interval, 出图实际耗时)   ← 降 tick 匹配
  ▼
F14 world-delta (features/f14_world_delta/handler.py:68)
  在增量里新增 frame 字段: { tick, url: "/api/hbm/frames/<tick>.png" }
  ▼
前端 useWorldDeltaPoll → worldDeltaApply (web/.../game-loop)
  └─ [新] FrameStage 组件：只显示最新已就绪帧（替换 WorldStage）
```

## 3. 分层改造点（落到真实文件）

### L0 配置 `config/prompts/`
- 新增 `config/prompts/scene_render/config.yaml`：模型 endpoint、`api_key_env`、
  `seed`、每帧 `steps`、`width/height`、`min_tick_interval_sec`、并发上限。
- 新增 `config/prompts/scene_render/scene_prompt.yaml`：**画面 prompt 模板**
  （全局画风前缀 + 房间布局描述 + 人物位置/动作槽位 + phase 氛围）。
- 新增 `config/prompts/scene_render/references/`：每个房间/关键场景的**参考图**
  （boardroom/lobby/office_a/office_b），供 IP-Adapter/ControlNet。
- `shared/prompt_paths.py` 加解析函数 `scene_render_config_path()` 等。

### L1 Runner `core/runner/`
- `world_loop.py:288` 的 `asyncio.sleep(interval)` 改为
  `asyncio.sleep(max(min_interval, last_render_elapsed))`（降 tick 匹配）。
- `world_step.run_one_tick()` 末尾挂一个 hook：tick 状态定型后调用出图服务。
  出图属 L2，按 D4 经 `core/runner/integration/` 白名单桥接，不直接 import feature。

### L2 新增 Feature `features/f18_scene_render/`（新模块）
| 文件 | 职责 |
|------|------|
| `__init__.py` | 公共 API：`render_tick_frame(tick, world_state) -> FrameRecord` |
| `client.py` | 极速文生图客户端（OpenAI-images 兼容或所选模型 REST），读 `DMXAPI_KEY`/独立 key |
| `prompt_builder.py` | 世界状态 → 画面 prompt（消费 §L0 模板 + 在场人物/发言/phase） |
| `consistency.py` | 固定 seed 选择 + 按当前房间取参考图，拼出图请求参数 |
| `store.py` | 落盘 `sim_dir/frames/<tick>.png` + 写 `frame` 表；reset 时清理 |
| `config.py` | 加载 `scene_render/*` 配置 |

> 复用现有 LLM 基建参考：密钥解析 `core/runner/kernel.py:88` 的
> `resolve_api_key`、客户端范式 `agent_world/llm/providers/openai_deepseek.py`。
> 出图客户端**新写**（图像 API 与 chat 不同），但密钥/错误映射沿用同套约定。

### L3 传输/前端
- **HTTP** `http/routes.py`：新增 `GET /simulations/<sim_id>/frames/<tick>.png`
  从 `sim_dir/frames/` 返回图片（`send_file`）；或在 world-delta 内嵌 base64（小图可选）。
- **world-delta** `features/f14_world_delta/handler.py:68`：返回对象加
  `"frame": {"tick": N, "url": ".../frames/N.png"}`。
- **前端**：
  - 新增 `web/src/features/frame-stage/`（FrameStage 组件 + hook），只渲染最新就绪帧
    （带上一帧兜底，避免加载空窗）。
  - `worldDeltaApply.ts:54` 解析 `frame` 字段，dispatch `SET_FRAME`。
  - `App.tsx` 用 FrameStage **替换** `WorldStage`；删除 `features/world-stage/`
    与相关 store/样式（完全替换）。story-mode 若复用世界舞台需同步改造。

### 持久化 `world.db`
- 新增 `frame` 表：`(tick INTEGER PRIMARY KEY, path TEXT, prompt TEXT, seed INTEGER,
  model TEXT, status TEXT, generated_at TEXT)`，DDL 放
  `agent_world/persistence/schema/world/`，`world_db.py` 加 `insert_frame()`。

## 4. 画面 prompt 组装（核心可玩性）

每 tick 从世界状态取：当前 phase、玩家所在房间、房间内在场 agent 及其角色、本 tick
正在发言者与内容摘要、近期 move 事件 → 套 `scene_prompt.yaml` 模板生成英文/中文
画面描述。固定全局画风前缀（如 "cinematic boardroom, semi-realistic, consistent
character design"）保证风格统一。

## 5. 一致性策略实现（固定种子 + 参考图）

- **seed**：每个房间一个固定 seed（office 同风格可共享），跨 tick 不变 → 同房间画面稳定。
- **参考图**：按当前房间取 `references/<place>.png` 作 IP-Adapter/ControlNet 条件，锁布局。
- 人物一致性进一步可加角色参考图（多 IP-Adapter）——视所选模型能力，列为 P2 增强。

## 6. tick 速率自适应（降 tick 匹配）

- 配置 `min_tick_interval_sec`（下限，比如 1.5s）。
- 每 tick 记录出图耗时 `elapsed`；下个 tick 间隔 = `max(min_interval, elapsed)`。
- 出图失败/超时：跳过该帧、保留上一帧、tick 照常推进（不阻塞世界逻辑）。
- `/world-loop/status` 暴露当前实际 tick 间隔与出图耗时，便于观测。

## 7. 完全替换前端的取舍

- 删除 `world-stage` 渲染 → 代码更干净，但**失去结构化交互**（点房间/看气泡）。
  若后续要点击交互，需在帧上叠加透明热区或保留少量 overlay——本分支按"纯看图"先做。
- story-mode 的对话历史/字幕面板**建议保留**（它消费 agent_messages，不依赖世界舞台像素），
  叠加在帧之上，信息不丢。

## 8. 分阶段实施（tracer bullet，小步可回归）

1. **P0 打通单帧**：写 `f18` 出图客户端 + 一个固定 prompt，手动触发出一张图存盘 → 验证模型/密钥/延迟。
2. **P1 接 tick**：world_step hook 调出图、写 frame 表、落盘；先不改 tick 速率。
3. **P2 下发与显示**：world-delta 加 frame 字段 + `/frames/<tick>.png` 路由 + 前端 FrameStage 显示（与旧 WorldStage 暂并存，便于对比）。
4. **P3 降 tick 匹配**：tick 间隔自适应 + 失败兜底。
5. **P4 一致性**：接固定 seed + 参考图，调 prompt 模板。
6. **P5 完全替换**：删 world-stage 及死代码，story-mode 叠加适配，门禁 + build 全绿。

> 每步后跑 `python3 scripts/test_m0_acceptance.py` + `cd web && npm run build`；
> 出图涉外部 API，E2E 默认降级跳过出图断言（仿 LLM Tier 策略）。

## 9. 关键风险 / 未决

- **极速模型一致性上限**：Turbo/LCM 类对 ControlNet/IP-Adapter 支持有限，整帧每 tick 仍
  可能闪变 → 可能要退到"图生图链"或自部署 GPU（路线再议）。
- **成本**：每 tick 一张图，长对局累积调用量大；需配额/缓存（相同状态可命中上帧）。
- **画面 prompt 质量**：世界状态→画面描述是新的主要工程量，决定观感。
- **完全替换不可逆**：建议 P5 前用 git 分支/双模式保留回退点，门禁绿再删旧渲染。
- **模型选型待定**：极速文生图的**具体服务/endpoint**未定（DMXAPI 是否提供图像端点需确认），
  P0 第一件事就是确认可用的出图 API。
