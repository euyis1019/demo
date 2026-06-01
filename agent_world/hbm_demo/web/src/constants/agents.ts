/** Agent 显示名：一律走后端下发的 name_map（覆盖当前故事全部角色，含中文），无写死名单。 */

export const PLAYER_AGENT_ID = "player";

/** F08 后端虚拟玩家实体 id；UI 位置以 {@link PLAYER_AGENT_ID} + player_place_id 为准。 */
export const VIRTUAL_PLAYER_AGENT_ID = "0";

export function agentDisplayName(
  agentId: string | number,
  nameMap?: Record<string, string>,
): string {
  if (String(agentId) === PLAYER_AGENT_ID) {
    return "玩家";
  }
  const key = String(agentId);
  if (nameMap?.[key]) {
    return nameMap[key];
  }
  return `角色 ${agentId}`;
}
