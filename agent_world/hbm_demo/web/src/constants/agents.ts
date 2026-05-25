/** HBM demo agent roster — aligned with scenario name_map. */

export const HBM_AGENT_IDS = [1, 2, 3, 4, 5, 6, 7] as const;

export type HbmAgentId = (typeof HBM_AGENT_IDS)[number];

export const AGENT_DISPLAY_NAMES: Record<number, string> = {
  1: "接待前台",
  2: "Jensen",
  3: "Tech VP",
  4: "AMD CEO",
  5: "Intel CEO",
  6: "Samsung CEO",
  7: "Sam Altman",
};

export const PLAYER_AGENT_ID = "player";

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
  const numeric = Number(agentId);
  if (!Number.isNaN(numeric) && AGENT_DISPLAY_NAMES[numeric]) {
    return AGENT_DISPLAY_NAMES[numeric];
  }
  return `Agent ${agentId}`;
}
