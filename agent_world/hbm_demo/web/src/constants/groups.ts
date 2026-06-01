/** GRP group_id 展示名：数据驱动——无写死故事专属群名，统一显示「群 #id」（后端如下发群名可在此接入）。 */

export function groupDisplayLabel(groupId: number | undefined): string | undefined {
  if (groupId === undefined) {
    return undefined;
  }
  return `群 #${groupId}`;
}
