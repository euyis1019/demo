// 玩家位置的非响应式共享 ref（高频更新不进 zustand，避免重渲染）。
// Player 写、CameraRig 读、zone 检测读。
export const playerRef = { x: -28, z: 8, facing: "down" as "down" | "up" | "left" | "right" };
