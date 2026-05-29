/** GRP group_id 展示名 — 对齐 hbm_scenario.yaml groups。 */

export const GROUP_LABELS: Record<number, string> = {
  100: "诊所小本本同步群",
  200: "社死任务临时群",
};

export function groupDisplayLabel(groupId: number | undefined): string | undefined {
  if (groupId === undefined) {
    return undefined;
  }
  return GROUP_LABELS[groupId] ?? `GRP #${groupId}`;
}
