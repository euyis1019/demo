/** 任务过渡提示：数据驱动——游戏是任务式的，后端下发的新「任务标题」(beats_label) 直接生成通用过渡文案，不写死任何故事。 */

export function getPhaseTransitionMessage(
  fromPhase: string,
  toPhase: string,
): string | undefined {
  if (!toPhase || fromPhase === toPhase) {
    return undefined;
  }
  return `新任务 · ${toPhase}`;
}
