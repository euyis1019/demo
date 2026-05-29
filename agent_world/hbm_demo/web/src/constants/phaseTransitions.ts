/** Phase 过渡文案 — SBTI clinic routing nodes A/B/C。 */

export const PHASE_TRANSITIONS: Record<string, string> = {
  "Phase 1->Phase 2": "前台掀开帘子，Morgen 医生已经把小本本翻到第一页",
  "Phase 2->Phase 3": "倒计时钟跳了一格，你被带进诅咒测评间",
  "Phase 3->Phase 4": "收音机和残影退场，最终 SBTI 诊断开始",
};

export function getPhaseTransitionMessage(
  fromPhase: string,
  toPhase: string,
): string | undefined {
  if (fromPhase === toPhase) {
    return undefined;
  }
  return PHASE_TRANSITIONS[`${fromPhase}->${toPhase}`];
}
