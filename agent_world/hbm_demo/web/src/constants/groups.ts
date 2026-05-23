/** GRP group_id 展示名 — 对齐 hbm_scenario.yaml groups。 */

export const GROUP_LABELS: Record<number, string> = {
  100: "NVIDIA 核心高管群",
  200: "HBM 价格联盟",
};

export function groupDisplayLabel(groupId: number | undefined): string | undefined {
  if (groupId === undefined) {
    return undefined;
  }
  return GROUP_LABELS[groupId] ?? `GRP #${groupId}`;
}
