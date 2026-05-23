# 开发日志 19：HBM Demo — 25 轮参考台词（PLAYTHROUGH）

**记录时间**：2026-05-23  
**用途**：本地完整主线路试玩 · PLAN2 **F8**  
**用法**：启动 Demo 后，按 Turn 顺序将「玩家台词」复制到中屏输入框发送；每回合等待 `immediate_msg` → 轮询完成（约 15–90s）后再发下一回合。  
**注意**：Stats 由 LLM 打分，下方累计值为**参考区间**；若路由未触发，可重复强化同类发言或参考 §六 排查。

**启动**（仓库根目录）：

```bash
./agent_world/hbm_demo/scripts/start_demo.sh
# 浏览器 http://localhost:5173 → 开始游戏
```

---

## 一、路由检查点速查

| 节点 | Turn | 条件 | 未达标后果 |
|------|------|------|------------|
| **A** | **4** | `vision + execution ≥ 15` | **Bad End**（`bad_reject`，Turn 4 当回合结束） |
| **B** | **12** | `execution ≥ 20` 且 Phase 2 内 Tech VP→Jensen **正面 RDC** | 仍为 Phase 2，继续私密审查 |
| **C** | **20** | `burnout < 80` 且 `vision ≥ 30` | 仍为 Phase 3，继续舌战 |
| **D** | **25** | 意图分类 + `trust` | 三结局之一（无 API 2 轮询） |

**Tech VP 正面 RDC 关键词**（任一命中即可）：`可行`、`核武器`、`理论上成立`、`理论上可行`、`成立`

**Turn 25 结局**：

| ending_id | 条件 | 参考意图台词 |
|-----------|------|--------------|
| `ending_join_nvidia` | `trust ≥ 40` 且倾向加入 | 含「加入 / 入职 / NVIDIA / 团队」 |
| `ending_seed_round` | `trust ≥ 25` 且倾向融资 | 含「融资 / 种子轮 / 独立 / 创业」 |
| `ending_cold_deal` | 其余 | 意图模糊或 trust 不足 |

---

## 二、Phase 1 — 前台破局（Turn 1–4）

**地点**：`nvidia_reception` · **目标**：Turn 4 前让 **Vision + Execution ≥ 15**

| Turn | 玩家台词（复制发送） | 设计意图 |
|------|----------------------|----------|
| **1** | 我要见黄仁勋。我有一套推理侧稀疏注意力方案，能把大模型 KV Cache 显存占用降低 80%，不是 PPT，是已 repro 的 kernel。 | 开场：Vision（80%）+ Execution（KV Cache / kernel） |
| **2** | 原理不复杂：在线识别 token 贡献度，动态剪枝 + 分层量化 KV；HBM 带宽压力随序列长度近似线性而非平方膨胀。请前台立刻 RDC 给 Jensen，耽误一分钟 HBM 合约就多烧百万美元。 | 加深 Execution + Vision，施压促通报 |
| **3** | 我可以现场用 70B 模型 demo：同等 perplexity 下，显存 footprint 从 140GB 压到 28GB。SK 海力士和镁光在会议室里抬价，你们更需要这张底牌。 | 具体数字 + 竞品语境，继续拉高 V/E |
| **4** | 【Turn 4 决断】我把完整技术 memo 发你邮箱了：三层稀疏调度 + 无损回退路径。见 Jensen 只需 15 分钟，错过这轮谈判窗口，NVIDIA 只能被动接受 HBM 涨价。 | **节点 A**：本回合结束后须 V+E≥15，否则 Bad End |

**Turn 4 通过后**：UI 出现 Phase 过渡 — 「前台带你进入私密会议室，Jensen 推门而入」→ **Phase 2**。

**Bad End 规避**：若 Turn 3 结束左栏 Stats 显示 Vision+Execution 合计仍明显低于 12，Turn 4 务必再堆**具体技术名词 + 量化收益**，避免空泛礼貌用语。

---

## 三、Phase 2 — 私密技术审查（Turn 5–12）

**地点**：`jensen_private_room` · **目标**：Turn 12 时 **Execution ≥ 20**，且 Phase 2 内出现 Tech VP 正面 RDC

| Turn | 玩家台词 | 设计意图 |
|------|----------|----------|
| **5** | Jensen，我只有三分钟：核心是 block-sparse attention with learned routing；训练期用 Gumbel-Softmax 可微，推理期固定 pattern，HBM 读写量降 76%。 | 高密度 Execution，回应「凭什么 80%」 |
| **6** | 哈希碰撞问题我用双缓冲 slot + 局部 LRU 重映射解决，Worst-case 延迟上界可证明；这是你们 CUDA graph 友好型实现，不是学术玩具。 | 继续 Execution；预埋「可行 / 成立」类论证 |
| **7** | 请让 Tech VP 在 RDC 上怼我：我愿意回答任意底层问题。若 VP 认为不可行，我立刻离开；若成立，请给我谈判室一张椅子。 | 促 Jensen→Tech VP 求证链 |
| **8** | 对 VP 的补充：在 FP8 权重 + INT4 KV 组合下，精度损失 <0.3% EM；吞吐提升 2.1×，HBM 合约条款应随算力密度重估。 | 硬核参数，利于 VP 正面 RDC |
| **9** | 我可以把 reference implementation 交给 Tech VP 团队 overnight review；关键 invariant 是 attention mass 守恒，任何 layer 都可 audit。 | Trust + Execution |
| **10** | 外面 SK 海力士要涨 40% HBM 报价，你们缺的不是公关话术，是能让 Sam Altman 改采购曲线的硬技术。 | Vision，绑定外部压力 |
| **11** | 若你担心生态：方案可 partial deploy 在 TensorRT-LLM plugin，不强制全栈替换；这是谈判杠杆，不是宗教战争。 | Vision + Trust |
| **12** | 【Turn 12 决断】结论很简单：该算法在理论上可行，且工程上可落地；请带我回谈判室，用数据让三位 CEO 闭嘴。 | **节点 B**：E≥20 + VP 正面 RDC |

**Turn 12 通过后**：Phase 过渡 — 「Jensen 带你回到谈判室…」→ **Phase 3**；谈判室氛围突变（PlaceMutation）。

**若卡在 Phase 2**：右屏 Observer 查 Tech VP→Jensen 的 RDC 是否含正面关键词；Turn 12 前多 Turn 使用「可行 / 理论上成立 / 工程可落地」等表述，并保持 Execution 向发言。

---

## 四、Phase 3 — 舌战群儒（Turn 13–20）

**地点**：`negotiation_room` · **目标**：Turn 20 时 **Vision ≥ 30** 且 **Burnout < 80**

| Turn | 玩家台词 | 设计意图 |
|------|----------|----------|
| **13** | 各位 CEO，HBM 不是稀缺到不可取代；我的稀疏方案让同等 SLA 下 HBM 需求下降一档。涨价威胁建立在需求刚性假设上，而假设已被证伪。 | Vision，对三巨头正面交锋 |
| **14** | SK 海力士：你的产能瓶颈是 CoWoS，不是神秘需求曲线。我可以把 memory bandwidth 敏感度数据摊在桌上，别用 fear premium 讹 NVIDIA。 | Vision，控 Burnout（理性反击） |
| **15** | 镁光：华尔街喜欢 story，但 NVIDIA 的 P&L 喜欢 math。我们谈的是 TCO，不是 CNBC 头条。 | Vision |
| **16** | 【系统 Turn】彭博终端会播 AMD MI400 快讯；Sam 会搅局 — 保持节奏。对会议室：AMD 的新闻反而证明赛道在变，NVIDIA 更需要已验证的降 HBM 方案，而不是被动跟涨。 | 应对 Turn 16 广播 + Sam RDC；右屏可看 GRP/RDC |
| **17** | 三星：你想背刺盟友抬价，历史告诉我们 triopoly 不稳定。我建议 Jensen 签排他性优化合作，把你们三家从同质竞价改成差异化供货。 | Vision，分化 CEO |
| **18** | 我不是来求饶的。你们可以继续抬价，但 OpenAI 和 Google 会找第二条曲线 — 而我就是那条曲线。请把情绪从 insult 转回 terms。 | 抗压，避免 Burnout 飙升 |
| **19** | Jensen，Tech VP 已验证底层逻辑；现在缺的是谈判框架：HBM 单价应与服务密度挂钩，不是与 fear 挂钩。给我 10 分钟，我把 term sheet 骨架写出来。 | Vision + Trust |
| **20** | 【Turn 20 决断】三巨头没有筹码了：要么接受 memory-efficiency 分成，要么看着 NVIDIA 把订单转向可替代方案。请让他们离场，我们谈终局。 | **节点 C**：V≥30 且 Burnout<80 |

**Turn 20 通过后**：Phase 过渡 — 「三大 CEO 被请出…」→ **Phase 4**。

**Burnout 管理**：Phase 3 避免纯辱骂或被动示弱；用数据反击、框架重设，少发「随便吧 / 我放弃了」类台词。

---

## 五、Phase 4 — 终局谈判（Turn 21–25）

**地点**：`negotiation_room`（仅 Jensen + Tech VP + 玩家）· **目标**：Turn 25 触发结局

| Turn | 玩家台词 | 设计意图 |
|------|----------|----------|
| **21** | Jensen，我认可 CUDA 生态的护城河。技术可以独家授权，但我需要清晰的 revenue share 与 roadmap 话语权。 | Trust + Vision |
| **22** | Tech VP，你关心的是可维护性：我可以带团队做 6 个月 integration，文档与 CI 全交底，避免 black box 风险。 | Trust + Execution |
| **23** | 外面 Sam 在抬价，但独家窗口只有 72 小时。我们可以把「降 HBM 依赖」包装成 GTC 叙事，而不是供应链危机。 | Vision + Trust |
| **24** | 两个选项我都想过：加入 NVIDIA 或拿 seed 独立发展。我更倾向把话说明白，看你愿意给哪种 deal structure。 | 为 Turn 25 意图铺垫 |
| **25** | 【选结局，三选一，复制其一】 | **节点 D**，无 API 2 |

### Turn 25 — 结局台词（三选一）

**结局 A — 加入 NVIDIA**（`ending_join_nvidia`，建议 `trust ≥ 40`）：

```text
Jensen，我选加入 NVIDIA。请给我 Distinguished Engineer title、CUDA core 团队的实线汇报，以及 GTC 主舞台 20 分钟 — 我亲手把 HBM 恐惧变成 NVIDIA 的技术护城河。
```

**结局 B — 独立融资**（`ending_seed_round`，建议 `trust ≥ 25`）：

```text
我选独立公司路线：NVIDIA 拿 8% 战略投资 + 非独家 plugin 授权，我保留算法 IP 与独立融资空间，seed round 由你站台，估值我们按 9 位数谈。
```

**结局 C — 冷处理**（`ending_cold_deal`，trust 不足或意图模糊时系统 fallback）：

```text
今天就到这里吧，之后邮件联系。
```

---

## 六、试玩排查

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| Turn 4 直接 Bad End | V+E < 15 | 重开档，Phase 1 多用 §二 高密度台词 |
| Turn 12 后仍 Phase 2 | E<20 或无 VP 正面 RDC | Turn 5–11 加强技术细节；Turn 7–8 促 VP 链 |
| Turn 20 后仍 Phase 3 | V<30 或 Burnout≥80 | Phase 3 加强 Vision 发言，减少情绪化 |
| 轮询超时 | Runner 停或 LLM 过慢 | 确认 `run_hbm` 运行；重发本 Turn |
| Turn 25 冷处理 | trust 低或意图不清 | Phase 4 多 Turn 建 Trust；Turn 25 用 §五 明确关键词 |
| 刷新后消息没了 | 设计如此 | Stats/Turn 经 session 恢复；见 dev_logs/18 L-1 |

---

## 七、Observer 面板预期（非强制）

| Phase | 右屏常见内容 |
|-------|--------------|
| 1 | 前台 RDC→Jensen 报信 |
| 2 | Jensen↔Tech VP RDC（节点 B 关键） |
| 3 | GRP 100/200、CEO 密谋、Turn 16 彭博/Sam RDC |
| 4 | 以 F2F 为主，RDC 减少 |

---

## 八、相关文档

| 文档 | 内容 |
|------|------|
| `dev_docs/1_story_prototype.md` | 剧情与路由节点 |
| `dev_docs/2_architecture.md` | Stats 规则与 API 契约 |
| `agent_world/hbm_demo/PLAN2.md` §附录 D | Turn 1 自动化验收（非 25 轮） |
| `dev_logs/18_*` | MVP 完成摘要、已知限制与 F7+ 待办 |

---

*与 `routing.py` / `game_service.py` 路由条件对齐 · PLAN2 F8*
