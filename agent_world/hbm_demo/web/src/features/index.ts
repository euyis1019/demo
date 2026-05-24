/**
 * F09 frontend feature registry — dev_logs/26 §4.3.
 * Root `components/` and `hooks/` remain compatibility shims.
 */

export const FEATURE_REGISTRY = {
  F09a: { name: "启动与恢复", path: "features/boot/" },
  F09b: { name: "主游戏循环", path: "features/game-loop/" },
  F09c: { name: "三栏布局", path: "features/layout/" },
  F09d: { name: "中屏 F2F", path: "features/main-chat/" },
  F09e: { name: "右栏 Observer", path: "features/observer/" },
  F09f: { name: "结局流", path: "features/endings/" },
  F09g: { name: "API 客户端", path: "api/" },
  F09h: { name: "全局状态", path: "store/" },
} as const;

export * from "./boot";
export * from "./game-loop";
export * from "./layout";
export * from "./main-chat";
export * from "./observer";
export * from "./endings";
export * from "./shared";
