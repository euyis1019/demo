/** 幕/相位过渡提示：数据驱动——直接用后端下发的新幕名(beats_label)生成通用过渡文案，不写死任何故事。 */

export function getPhaseTransitionMessage(
  fromPhase: string,
  toPhase: string,
): string | undefined {
  if (!toPhase || fromPhase === toPhase) {
    return undefined;
  }
  return `进入「${toPhase}」`;
}
