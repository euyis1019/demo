/**
 * F2 静态 Mock — Turn 1 Phase 1 前台场景（PLAN2 F2 验收 / dev_logs/03）。
 * F3 起由 store + API 替换。
 */

import type { GameMessage, Stats } from "../api/types";
import { placeDisplayName } from "../utils/places";

export const MOCK_STATS: Stats = {
  vision: 8,
  execution: 5,
  trust: 12,
  burnout: 2,
};

export const MOCK_PHASE = "Phase 1";
export const MOCK_PLAYER_TURN = 1;
export const MOCK_MAX_TURNS = 25;
export const MOCK_PLACE_ID = "nvidia_reception";

export const MOCK_PLACE_LABEL = placeDisplayName(MOCK_PLACE_ID);
export const MOCK_PRESENT_AGENTS = ["接待前台"];

export const MOCK_IMMEDIATE_MSG =
  "前台接待员微微挑眉，停下了手中的咖啡杯，转身朝内厅方向看了一眼…";

/** 中屏：仅 F2F */
export const MOCK_F2F_MESSAGES: GameMessage[] = [
  {
    sender: "接待前台",
    content: "您好，请问有什么可以帮您？",
    type: "F2F",
    attempted_at: 1,
    place_id: MOCK_PLACE_ID,
  },
  {
    sender: "玩家",
    content: "我的算法能把显存消耗降低 80%。",
    type: "F2F",
    attempted_at: 2,
    place_id: MOCK_PLACE_ID,
  },
  {
    sender: "接待前台",
    content: "请稍等，我联系黄总。",
    type: "F2F",
    attempted_at: 5,
    place_id: MOCK_PLACE_ID,
  },
];

/** 右屏 Tab RDC */
export const MOCK_RDC_MESSAGES: GameMessage[] = [
  {
    sender: "接待前台",
    recipient: "Jensen Hwang",
    content:
      "黄总，前台有位来访者声称有革命性降显存算法，数值上看起来不像骗子。",
    type: "RDC",
    attempted_at: 6,
  },
  {
    sender: "Jensen Hwang",
    recipient: "Tech VP",
    content: "把技术 VP 拉进来，我要听第一手评估。",
    type: "RDC",
    attempted_at: 7,
  },
  {
    sender: "彭博终端",
    recipient: "Jensen Hwang",
    content:
      "彭博终端快讯：AMD 宣布下一代 MI400 将采用全新自研显存架构，市场震动。",
    type: "RDC",
    attempted_at: 8,
  },
];

/** 右屏 Tab GRP */
export const MOCK_GRP_MESSAGES: GameMessage[] = [
  {
    sender: "Micron CEO",
    content: "SK 那边已经松口了，我们不能再单独扛价。",
    type: "GRP",
    group_id: 200,
    attempted_at: 9,
  },
  {
    sender: "SK Hynix CEO",
    content: "英伟达今天态度很强硬，先观望 Jensen 的底牌。",
    type: "GRP",
    group_id: 200,
    attempted_at: 10,
  },
];
