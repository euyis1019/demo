/** F09 + F11–F16 frontend feature registry — dev_logs/26 §4.3, dev_logs/38 §R4 */

export const FEATURE_REGISTRY = {
  F09a: { name: "启动与恢复", path: "features/boot/" },
  F09b: {
    name: "主游戏循环",
    path: "features/game-loop/",
    note: "含 F11/F13/F14/F16 前端 delta 同步与 loop 控制",
  },
  F09c: { name: "两栏布局", path: "features/layout/" },
  F09d: { name: "玩家输入", path: "features/player-input/" },
  F09e: { name: "共享 UI", path: "features/shared/" },
  F09f: { name: "结局流", path: "features/endings/" },
  F09g: { name: "API 客户端", path: "api/" },
  F09h: { name: "全局状态", path: "store/" },
  F11: { name: "回合内增量同步", path: "features/game-loop/" },
  F12: { name: "四房间世界视图", path: "features/world-stage/" },
  F13: { name: "世界 loop 暂停/继续", path: "features/game-loop/" },
  F14: { name: "常驻 world delta", path: "features/game-loop/" },
  F15: { name: "Prompt Inspector", path: "features/prompt-trace/" },
  F16: { name: "WebSocket delta 推送", path: "features/game-loop/" },
  F18: { name: "AIGC 实时整帧画面", path: "features/story-mode/", note: "剧情模式舞台改为后端实时出图" },
  Story: { name: "沉浸式剧情模式", path: "features/story-mode/" },
} as const;

export * from "./boot";
export * from "./game-loop";
export * from "./layout";
export * from "./player-input";
export * from "./endings";
export * from "./shared";
export * from "./world-stage";
export * from "./prompt-trace";
export * from "./story-mode";
