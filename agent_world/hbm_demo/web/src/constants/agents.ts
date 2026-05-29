/** Dark SBTI clinic agent roster — aligned with scenario name_map. */

export const HBM_AGENT_IDS = [1, 2, 3, 4, 5, 6, 7] as const;

export type HbmAgentId = (typeof HBM_AGENT_IDS)[number];

export const AGENT_DISPLAY_NAMES: Record<number, string> = {
  1: "诊所前台",
  2: "Dr. Morgen",
  3: "黑猫",
  4: "老式收音机",
  5: "倒计时钟",
  6: "SUBJECT-0",
  7: "最近联系人",
};

export const PLAYER_AGENT_ID = "player";

/** F08 后端虚拟玩家实体 id；UI 位置以 {@link PLAYER_AGENT_ID} + player_place_id 为准。 */
export const VIRTUAL_PLAYER_AGENT_ID = "0";

export function agentDisplayName(
  agentId: string | number,
  nameMap?: Record<string, string>,
): string {
  if (String(agentId) === PLAYER_AGENT_ID) {
    return "你";
  }
  const key = String(agentId);
  if (nameMap?.[key]) {
    return nameMap[key];
  }
  const numeric = Number(agentId);
  if (!Number.isNaN(numeric) && AGENT_DISPLAY_NAMES[numeric]) {
    return AGENT_DISPLAY_NAMES[numeric];
  }
  return `Agent ${agentId}`;
}
