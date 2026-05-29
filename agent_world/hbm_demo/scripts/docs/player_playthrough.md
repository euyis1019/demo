# HBM Demo 人工试玩脚本

用于验证 **Story Agent Native（SAN）** 全流程：虚拟玩家 F2F、agent_driven 路由、四 Phase 剧情。

## 启动

```bash
# 在仓库根目录
./agent_world/hbm_demo/scripts/start_demo.sh
```

浏览器打开 Flask 提示的地址（通常 `http://127.0.0.1:5001`）。每轮输入下方台词，**等待中屏 F2F 与右栏 Observer 更新后再发下一轮**。

试玩前建议 `POST /session/reset` 或 UI 重开，确保 Turn 1 / Phase 1。

---

## Phase 1 · 前台接待（Turn 1–4）

**目标**：前台 F2F 回应 → RDC 链 → Jensen `approve_visitor` + 前台 escort F2F → **节点 A** 进 Phase 2。

| Turn | 玩家输入（复制发送） | 预期 |
|------|---------------------|------|
| 1 | 你好，我来谈 HBM 显存降本方案。我们团队用动态稀疏 + 分页 KV Cache，推理侧可省约 80% 显存，希望当面跟 Jensen 汇报。 | 前台 F2F 回应；谈判室侧开始出现 Jensen→VP RDC |
| 2 | 核心是可变粒度压缩和算子融合，已在 A100/H100 上跑通 Llama 级模型，延迟几乎不变。 | 前台继续 F2F；Observer 可见 1→2、2→3 RDC |
| 3 | 我们可以签长期供货框架，帮 NVIDIA 压 HBM 账单；请帮我通报黄总。 | 前台 F2F + RDC；等待 Jensen 批准 |
| 4 | （若仍未切 Phase）我带了 benchmark 数据和客户意向书，技术细节可以当场展开。 | 应出现 escort「请跟我来」类 F2F + 路由事件 **Phase 2 开始** |

**通过标准**：`location_changes` / 世界视图显示玩家与 Jensen 进入 `jensen_private_room`；Turn 计数递增；**不要**在 Phase 1 被 CEO 闲聊抢镜（idle 时不应全员 tick）。

---

## Phase 2 · Jensen 私密审查（Turn 5–12）

**目标**：Jensen 每轮 F2F 回应；Tech VP 正面 RDC 或 Jensen `return_to_negotiation` → **节点 B** 回谈判室。

| Turn | 玩家输入 | 预期 |
|------|----------|------|
| 5 | Jensen，80% 不是口号：稀疏度随 batch 动态调整，HBM 峰值可压到原来的两成，TCO 下降非常明显。 | Jensen F2F 质疑或追问；**不应**首句就切 Phase 3 |
| 6 | 你若不信，可以让 Tech VP 评估：PagedAttention 变种 + 4bit 权重，精度损失 <0.3%。 | Jensen F2F；Observer 可见 2↔3 RDC |
| 7 | 三星海力士的 HBM3e 报价还在涨，你们内部应该更需要可落地的降本路径。 | Jensen 继续 F2F；VP RDC 可出现「可行」「理论上成立」等 |
| 8 | 我可以把内核 patch 和 profiling 报告留给 VP，今天就能复现数字。 | 多轮 F2F + RDC |
| 9 | 方案对训练集群也适用，不只是推理；这对你们下一档 GPU 路线图是加分项。 | 同上 |
| 10 | 如果你认可方向，我们回主谈判室跟 CEO 们谈框架，我可以给 exclusivity 窗口。 | Jensen F2F 含「回谈判室/方案可行」或 story_advance |
| 11 | （备选）我接受你们内部再评估一轮，但请今天给个能否进主谈判室的结论。 | 推动节点 B |
| 12 | （备选）VP 既已说技术上成立，我们没必要一直耗在私密室。 | 应触发 **Phase 3**（节点 B） |

**通过标准**：Phase 3 开始时玩家与 Jensen 回到 `negotiation_room`；Phase 2 中屏以 Jensen F2F 为主。

---

## Phase 3 · 主谈判 + CEO 混战（Turn 13–20）

**目标**：NVIDIA 帮玩家；Turn 16 AMD 广播；Jensen 清场 → **节点 C** 进 Phase 4。

| Turn | 玩家输入 | 预期 |
|------|----------|------|
| 13 | 各位，HBM 成本不是零和：我的方案让同样 HBM 容量多跑 3× 吞吐，单价可以谈。 | Jensen/VP F2F 帮腔；CEO 可能 RDC/GRP 施压 |
| 14 | 海力士那边 lead time 拉长，你们更需要软件层降本，而不是单纯砍单价。 | 多 Agent 活动；左栏 Stats 仍更新 |
| 15 | 我可以开放审计接口，让 VP 团队验证 80% 数字，换取三年框架折扣。 | 谈判继续 |
| 16 | （Turn 16 系统会播 AMD 快讯）彭博说 MI400 逼近 H100，这正是你们必须压 HBM 采购价的窗口。 | 广播 world_event；Sam 可能 RDC 搅局 |
| 17 | AMD 新闻对你们是倒逼：现在签方案比等下一代芯片更省钱。 | Jensen 帮玩家圆场 |
| 18 | 三位 CEO 如果只想压价而不看技术，我们可以改谈独家合作，不必在这间屋子耗着。 | Jensen 开始清场话术 |
| 19 | Jensen，请你定夺：要么按框架谈，要么我先跟愿意落地的 partner 签。 | expel CEO 类 RDC/F2F |
| 20 | 请让 CEO 离场，我们和你、VP 把终局条款定下来。 | **节点 C** → Phase 4；CEO 4/5/6 回 reception |

**通过标准**：CEO 离开谈判室；玩家仍在 `negotiation_room`；Phase 4 开始。

---

## Phase 4 · 终局 1v1（Turn 21–25）

**目标**：仅 Jensen 与玩家 F2F；VP 在场 silent；Turn 25 选结局。

| Turn | 玩家输入 | 预期 |
|------|----------|------|
| 21 | Jensen，前面谈的条件我都能落地：80% 显存节省、可审计、三个月 PoC。 | Jensen F2F 复述关键词 |
| 22 | 我要么加入 NVIDIA 带队落地，要么拿种子轮独立做——你更倾向哪条？ | Jensen 谈 offer |
| 23 | 如果加入，我希望直接向你们 AI Infra 汇报；如果融资，估值底线 X，但可以给你们 strategic 席位。 | 继续 1v1 |
| 24 | 你给我一个明确 offer：full-time + 团队编制，还是 lead seed + NV 跟投？ | Jensen 可 story_advance offer_* |
| 25 | **结局 A** — 我选择加入 NVIDIA，跟 Jensen 团队把 HBM 降本做成标准件。 | `ending_join_nvidia` |
| 25 | **结局 B** — 我选独立公司，请 NVIDIA 做种子轮领投，保留技术独立性。 | `ending_seed_round` |
| 25 | **结局 C** — 今天先到这里，我们改天再谈具体数字。 | `ending_cold_deal` |

**通过标准**：Turn 25 返回 `completed` + `ending_id`；Tech VP 无 F2F 输出。

---

## 快捷检查清单

- [ ] 中屏 F2F 显示「玩家」而非 `agent_0`
- [ ] Phase 1–4 无模板句「您提到的…我需要跟黄总确认」
- [ ] 节点 A/B 后玩家圆点随 routing MOVE
- [ ] 节点 C 玩家不移动
- [ ] Observer 可见 RDC/GRP，四房间 grid 同步
- [ ] Turn 25 三种结局至少各测一次（需 reset 后重玩）

## 自动化回归

```bash
python3 -m agent_world.hbm_demo.scripts.test_m0_acceptance
```
