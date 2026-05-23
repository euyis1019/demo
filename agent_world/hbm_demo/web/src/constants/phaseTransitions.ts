/** Phase 过渡文案 — PLAN2 F4-6 / dev_docs 路由节点 A/B/C。 */

export const PHASE_TRANSITIONS: Record<string, string> = {
  "Phase 1->Phase 2": "前台带你进入私密会议室，Jensen 推门而入",
  "Phase 2->Phase 3": "Jensen 带你回到谈判室，三大 CEO 齐刷刷看向你",
  "Phase 3->Phase 4": "三大 CEO 被请出，终局谈判开始",
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
