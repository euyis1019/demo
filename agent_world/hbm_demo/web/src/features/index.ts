/** F09 + F12 frontend feature registry — dev_logs/26 §4.3, dev_logs/32 §6. */

export const FEATURE_REGISTRY = {
  F09a: { name: "启动与恢复", path: "features/boot/" },
  F09b: { name: "主游戏循环", path: "features/game-loop/" },
  F09c: { name: "两栏布局", path: "features/layout/" },
  F09d: { name: "玩家输入", path: "features/main-chat/PlayerInput.tsx" },
  F09f: { name: "结局流", path: "features/endings/" },
  F09g: { name: "API 客户端", path: "api/" },
  F09h: { name: "全局状态", path: "store/" },
  F12: { name: "四房间世界视图", path: "features/world-stage/" },
  Story: { name: "沉浸式剧情模式", path: "features/story-mode/" },
} as const;

export * from "./boot";
export * from "./game-loop";
export * from "./layout";
export * from "./main-chat";
export * from "./endings";
export * from "./shared";
export * from "./world-stage";
export * from "./prompt-trace";
export * from "./story-mode";
