// UI 是否抢占输入（聊天输入框聚焦时禁玩家走动）。后续聊天面板用它。
let _focused = false;
export function setUiFocused(v: boolean) {
  _focused = v;
}
export function isUiFocused(): boolean {
  return _focused;
}
