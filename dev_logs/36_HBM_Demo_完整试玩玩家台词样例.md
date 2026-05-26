# 开发日志 36：HBM Demo — 完整试玩玩家台词样例

**记录时间**：2026-05-23  
**用途**：人工完整通关 · 每 Turn 复制一句发送 · **仅玩家台词**  
**用法**：`POST /session/reset` 或 UI 重开后，按 Turn 1→25 顺序发送；每轮等中屏 F2F 更新后再发下一句。Turn 25 三选一。

---

## Turn 1

你好，我来谈 HBM 显存降本方案。我们团队用动态稀疏 + 分页 KV Cache，推理侧可省约 80% 显存，希望当面跟 Jensen 汇报。

## Turn 2

核心是可变粒度压缩和算子融合，已在 A100/H100 上跑通 Llama 级模型，延迟几乎不变。请前台立刻 RDC 给 Jensen，耽误一分钟 HBM 合约就多烧百万美元。

## Turn 3

我们可以签长期供货框架，帮 NVIDIA 压 HBM 账单；请帮我通报黄总。同等 perplexity 下，显存 footprint 从 140GB 压到 28GB，SK 海力士正在会议室里抬价。

## Turn 4

我带了 benchmark 数据和客户意向书，技术细节可以当场展开。见 Jensen 只需 15 分钟，错过这轮谈判窗口，NVIDIA 只能被动接受 HBM 涨价。

## Turn 5

Jensen，80% 不是口号：稀疏度随 batch 动态调整，HBM 峰值可压到原来的两成，TCO 下降非常明显。核心是 block-sparse attention with learned routing，推理期固定 pattern，HBM 读写量降 76%。

## Turn 6

你若不信，可以让 Tech VP 评估：PagedAttention 变种 + 4bit 权重，精度损失 <0.3%。哈希碰撞用双缓冲 slot + 局部 LRU 重映射，Worst-case 延迟上界可证明。

## Turn 7

请让 Tech VP 在 RDC 上怼我：我愿意回答任意底层问题。若 VP 认为不可行我立刻离开；若理论上成立，请给我谈判室一张椅子。三星海力士的 HBM3e 报价还在涨，你们更需要可落地的降本路径。

## Turn 8

我可以把内核 patch 和 profiling 报告留给 VP，今天就能复现数字。在 FP8 权重 + INT4 KV 组合下，精度损失 <0.3% EM，吞吐提升 2.1×，HBM 合约条款应随算力密度重估。

## Turn 9

方案对训练集群也适用，不只是推理；这对你们下一档 GPU 路线图是加分项。关键 invariant 是 attention mass 守恒，任何 layer 都可 audit，reference implementation 可 overnight review。

## Turn 10

如果你认可方向，我们回主谈判室跟 CEO 们谈框架，我可以给 exclusivity 窗口。外面 SK 海力士要涨 40% HBM 报价，你们缺的是能让 Sam Altman 改采购曲线的硬技术，不是公关话术。

## Turn 11

我接受你们内部再评估一轮，但请今天给个能否进主谈判室的结论。方案可 partial deploy 在 TensorRT-LLM plugin，不强制全栈替换，这是谈判杠杆，不是宗教战争。

## Turn 12

VP 既已说技术上成立，我们没必要一直耗在私密室。结论很简单：该算法在理论上可行且工程上可落地，请带我回谈判室，用数据让三位 CEO 闭嘴。

## Turn 13

各位，HBM 成本不是零和：我的方案让同样 HBM 容量多跑 3× 吞吐，单价可以谈。涨价威胁建立在需求刚性假设上，而假设已被证伪。

## Turn 14

海力士那边 lead time 拉长，你们更需要软件层降本，而不是单纯砍单价。你的产能瓶颈是 CoWoS，不是神秘需求曲线，别用 fear premium 讹 NVIDIA。

## Turn 15

我可以开放审计接口，让 VP 团队验证 80% 数字，换取三年框架折扣。镁光：华尔街喜欢 story，但 NVIDIA 的 P&L 喜欢 math，我们谈 TCO，不是 CNBC 头条。

## Turn 16

彭博说 MI400 逼近 H100，这正是你们必须压 HBM 采购价的窗口。AMD 的新闻反而证明赛道在变，NVIDIA 更需要已验证的降 HBM 方案，而不是被动跟涨。

## Turn 17

AMD 新闻对你们是倒逼：现在签方案比等下一代芯片更省钱。我建议 Jensen 签排他性优化合作，把三家从同质竞价改成差异化供货。

## Turn 18

三位 CEO 如果只想压价而不看技术，我们可以改谈独家合作，不必在这间屋子耗着。我不是来求饶的，OpenAI 和 Google 会找第二条曲线，而我就是那条曲线。

## Turn 19

Jensen，请你定夺：要么按框架谈，要么我先跟愿意落地的 partner 签。Tech VP 已验证底层逻辑，HBM 单价应与服务密度挂钩，不是与 fear 挂钩。

## Turn 20

请让 CEO 离场，我们和你、VP 把终局条款定下来。三巨头没有筹码了：要么接受 memory-efficiency 分成，要么看着 NVIDIA 把订单转向可替代方案。

## Turn 21

Jensen，前面谈的条件我都能落地：80% 显存节省、可审计、三个月 PoC。我认可 CUDA 生态的护城河，技术可以独家授权，但我需要清晰的 revenue share 与 roadmap 话语权。

## Turn 22

我要么加入 NVIDIA 带队落地，要么拿种子轮独立做——你更倾向哪条？Tech VP 关心的是可维护性：我可以带团队做 6 个月 integration，文档与 CI 全交底，避免 black box 风险。

## Turn 23

如果加入，我希望直接向你们 AI Infra 汇报；如果融资，估值底线我们可以按 9 位数谈，但可以给你们 strategic 席位。外面 Sam 在抬价，独家窗口只有 72 小时，我们可以把降 HBM 依赖包装成 GTC 叙事。

## Turn 24

你给我一个明确 offer：full-time + 团队编制，还是 lead seed + NV 跟投？两个选项我都想过，我更倾向把话说明白，看你愿意给哪种 deal structure。

## Turn 25（结局 A — 加入 NVIDIA）

Jensen，我选加入 NVIDIA。请给我 Distinguished Engineer title、CUDA core 团队的实线汇报，以及 GTC 主舞台 20 分钟——我亲手把 HBM 恐惧变成 NVIDIA 的技术护城河。

## Turn 25（结局 B — 独立融资）

我选独立公司路线：NVIDIA 拿 8% 战略投资 + 非独家 plugin 授权，我保留算法 IP 与独立融资空间，seed round 由你站台，估值我们按 9 位数谈。

## Turn 25（结局 C — 冷处理）

今天就到这里吧，之后邮件联系。
