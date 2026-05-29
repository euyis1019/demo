export const DEV_STORY = {
  title: "暗黑心理诊所 · SBTI 黑色幽默测试",
  summary:
    "玩家在雨夜进入暗黑心理诊所，本以为要测 MBTI，实际被 Dr. Morgen、黑猫和一组异常资产带入 SBTI 测试。测试会记录玩家选择，并在后半段反转为记忆审判和社死任务。",
};

export const DEV_PHASES = [
  {
    id: "Phase 1",
    title: "候诊前台",
    rule: "前台接待玩家；玩家明确想测试后触发 Morgen 诊疗室。",
  },
  {
    id: "Phase 2",
    title: "Morgen 诊疗室",
    rule: "围绕派对、在吗、团建、透明药水推进 SBTI 四题，并记录玩家倾向。",
  },
  {
    id: "Phase 3",
    title: "诅咒测评间",
    rule: "身份反转、透明化预览、SUBJECT-0 线索和社死任务集中出现。",
  },
  {
    id: "Phase 4",
    title: "最终诊断",
    rule: "Morgen 根据玩家选择归档为死要面子型、猴急型或稻草人型。",
  },
];

export const DEV_ENDINGS = [
  {
    id: "ending_dead_type",
    title: "死要面子型",
    rule: "偏回避、嘴硬、在关键社交选择里优先维护体面。",
  },
  {
    id: "ending_monkey_type",
    title: "猴急型",
    rule: "偏冲动、直接、愿意快速行动甚至当场社死。",
  },
  {
    id: "ending_scarecrow_type",
    title: "稻草人型",
    rule: "偏犹豫、外表镇定但内心被风吹倒，常用拖延换安全感。",
  },
];

export const DEV_AGENT_PROMPTS = [
  {
    id: 1,
    name: "诊所前台",
    prompt:
      "过劳但礼貌的剧场检票员。玩家未开口时只说一句欢迎；玩家要测试时先 F2F 回应，再 RDC 汇报 Morgen。",
  },
  {
    id: 2,
    name: "Dr. Morgen",
    prompt:
      "暗黑心理诊所主治医生。主持 SBTI 测试，善用黑色幽默和记忆审判，最终给出人格归档。",
  },
  {
    id: 3,
    name: "黑猫",
    prompt:
      "诊所异常资产，负责短促吐槽和样本记录。只补刀，不科普。",
  },
  {
    id: 4,
    name: "老式收音机",
    prompt:
      "像信号不良的老电台，负责播报社死任务和不合时宜的提示。",
  },
  {
    id: 5,
    name: "倒计时钟",
    prompt:
      "用时间压力制造不适感，提醒测试不是普通问卷。",
  },
  {
    id: 6,
    name: "SUBJECT-0",
    prompt:
      "上一批实验体残影，用碎片闪回暗示玩家身份反转。",
  },
  {
    id: 7,
    name: "最近联系人",
    prompt:
      "外部社交压力来源，以微信弹窗式短句推动社死任务。",
  },
];

