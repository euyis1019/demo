// 世界布局（从 Godot config.gd 换算到 Three.js：XZ 平面，y 向上）。
// 三地点横排：农场左 / 广场中 / 酒馆右。后端只有离散 place，地点内坐标全是前端表现层。

export type Rect = { x: number; z: number; w: number; d: number }; // XZ 矩形

export const PLACE_RECTS: Record<string, Rect> = {
  farm: { x: -42, z: -15, w: 28, d: 30 },
  square: { x: -9, z: -13, w: 18, d: 26 },
  saloon: { x: 14, z: -15, w: 28, d: 30 },
};

export const PLACE_NAMES: Record<string, string> = {
  farm: "农场",
  square: "广场",
  saloon: "酒馆",
};

export const PLACE_CENTER: Record<string, [number, number]> = {
  farm: [-28, 0],
  square: [0, 0],
  saloon: [28, 0],
};

// 各地点站位锚点（XZ），NPC 到达后按到场序轮用
export const ANCHORS: Record<string, [number, number][]> = {
  farm: [[-28, -2], [-24, 4], [-32, 3], [-26, -7]],
  square: [[-2, -1], [3, 3], [-4, 4], [2, -4]],
  saloon: [[26, -2], [30, 4], [22, 3], [28, -6]],
};

export const PLAYER_SPAWN: [number, number] = [-28, 8]; // XZ
export const WORLD = { x: -44, z: -17, w: 88, d: 34 };

// agent 主题色（名牌/心情点）
export const NPC_COLORS: Record<number, string> = {
  0: "#8cd98c",
  1: "#f2c64d",
  2: "#e67380",
  3: "#f29940",
};

export const PLAYER_SPEED = 7.0; // 单位/s
export const NPC_SPEED = 4.0;
export const E_TALK_DISTANCE = 5.0;
export const SEND_THROTTLE = 0.3; // s，同类命令最小间隔
export const CAM_SIZE = 22; // 正交相机视野高（单位，越大看得越多）
export const BUBBLE_SECONDS = 5.0;

// 某地点第 idx 个锚点（环形复用）
export function anchorOf(place: string, idx: number): [number, number] {
  const arr = ANCHORS[place] ?? [[0, 0]];
  return arr[((idx % arr.length) + arr.length) % arr.length];
}

// XZ 点落在哪个地点（内缩矩形做滞后，避免边界抖动）；无则 ""
export function placeAt(x: number, z: number, shrink = 0): string {
  for (const [pid, r] of Object.entries(PLACE_RECTS)) {
    if (
      x >= r.x + shrink &&
      x <= r.x + r.w - shrink &&
      z >= r.z + shrink &&
      z <= r.z + r.d - shrink
    )
      return pid;
  }
  return "";
}

// 好感度 5 档（与后端 prompts/affinity.py::LEVELS 阈值一致）——焐心小镇支柱1
export const AFFINITY_TIERS = ["陌生", "熟悉", "友好", "亲密", "挚友"];
export function affinityTier(score: number): number {
  if (score >= 80) return 4;
  if (score >= 60) return 3;
  if (score >= 40) return 2;
  if (score >= 20) return 1;
  return 0;
}
export function affinityLevel(score: number): string {
  return AFFINITY_TIERS[affinityTier(score)];
}

// 世界时间 HH:MM → 时段牌（与后端 config.day_phase 阈值一致）——焐心小镇支柱2
export function dayPhase(worldTime: string): { label: string; icon: string } {
  const hour = parseInt((worldTime || "").split(":")[0], 10);
  if (isNaN(hour)) return { label: "", icon: "🕐" };
  if (hour >= 5 && hour <= 10) return { label: "清晨", icon: "🌅" };
  if (hour >= 11 && hour <= 15) return { label: "晌午", icon: "☀️" };
  if (hour >= 16 && hour <= 19) return { label: "傍晚", icon: "🌇" };
  return { label: "夜里", icon: "🌙" };
}

// 街坊作息倾向提示（避免盲目扑空；mirror soul 作息，按 agent_id 契约）
export const NPC_TENDENCY: Record<number, string> = {
  1: "白天守店，傍晚常去酒馆",
  2: "白天酒馆清闲，入夜最忙",
  3: "天亮下地，午后歇晌，傍晚串门",
};

// 简易地形高度（缓坡，单一真相源；与渲染、贴地共用）
export function groundY(x: number, z: number): number {
  return (
    Math.sin(x * 0.18) * 0.18 + Math.cos(z * 0.16) * 0.18 + Math.sin((x + z) * 0.07) * 0.15
  );
}
