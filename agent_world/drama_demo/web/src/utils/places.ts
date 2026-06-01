/** 地点工具：完全数据驱动——地点全集与显示名一律来自后端世界状态，不写死任何故事的地点。 */

import type { GameMessage } from "../api/types";

/** 地点 id 是任意字符串（各故事不同，可中文，如「后庭院」）。 */
export type PlaceId = string;

/**
 * 地点显示名。Story Pack 的 place_id 本身通常就是人读名（多为中文），直接显示即可；
 * 若后端 snapshot 提供了权威 place→name 映射，调用方可传 namesById 覆盖。
 */
export function placeDisplayName(
  placeId: string,
  namesById?: Record<string, string>,
): string {
  return namesById?.[placeId] || placeId || "";
}

/** 初始空房间表：空对象，由后端 snapshot/delta 下发的真实地点 key 填充。 */
export function emptyRoomF2f(): Record<string, GameMessage[]> {
  return {};
}

/**
 * 从世界状态派生「当前世界有哪些地点」——玩家所在 ∪ 各 agent 所在 ∪ roomF2f 报来的地点 key。
 * （后端 world-delta 的 room_f2f 一定带上活跃故事的全部地点 key，含空地点，故这是地点全集的可靠来源。）
 * 玩家所在地点置于首位、其余字典序，保证渲染顺序稳定。
 */
export function deriveWorldPlaces(
  playerPlaceId: string,
  agentLocations: Record<string, { placeId: string }>,
  roomF2f: Record<string, unknown>,
): string[] {
  const set = new Set<string>();
  if (playerPlaceId) set.add(playerPlaceId);
  for (const loc of Object.values(agentLocations)) {
    if (loc?.placeId) set.add(loc.placeId);
  }
  for (const key of Object.keys(roomF2f)) set.add(key);
  const rest = [...set].filter((p) => p !== playerPlaceId).sort();
  return playerPlaceId ? [playerPlaceId, ...rest] : rest;
}
