import type { CSSProperties } from "react";
import { PLAYER_AGENT_ID } from "../../../constants/agents";
import { agentsInPlace } from "../../../store/worldSync";

/** Agent circle position inside a room cell (percent). Shared by UI + RDC overlay. */
export function cellLocalPercent(index: number, total: number): { x: number; y: number } {
  if (total <= 1) {
    return { x: 50, y: 52 };
  }
  if (total === 2) {
    return { x: index === 0 ? 32 : 68, y: 52 };
  }

  const cols = Math.min(3, Math.ceil(Math.sqrt(total)));
  const rows = Math.ceil(total / cols);
  const col = index % cols;
  const row = Math.floor(index / cols);
  const xPad = 14;
  const yPad = 18;
  const xSpan = 100 - xPad * 2;
  const ySpan = 100 - yPad * 2;
  return {
    x: xPad + (xSpan * (col + 0.5)) / cols,
    y: yPad + (ySpan * (row + 0.5)) / rows,
  };
}

export function cellLocalStyle(index: number, total: number): CSSProperties {
  const { x, y } = cellLocalPercent(index, total);
  return { left: `${x}%`, top: `${y}%` };
}

/** Map agent id → center point on the dynamic room grid (0–100).
 *  places/cols/rows 来自 RoomGrid 同一份动态地点布局，保证 RDC 连线落点与房间格子对齐。 */
export function agentGridCenter(
  agentId: string,
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>,
  places: string[],
  cols: number,
  rows: number,
): { x: number; y: number } | null {
  const loc = agentLocations[agentId];
  if (!loc) {
    return null;
  }
  const cellIdx = places.indexOf(loc.placeId);
  if (cellIdx < 0 || cols < 1 || rows < 1) {
    return null;
  }
  const col = cellIdx % cols;
  const row = Math.floor(cellIdx / cols);

  const inPlace = agentsInPlace(agentLocations, loc.placeId);
  const index = inPlace.indexOf(agentId);
  if (index < 0) {
    return null;
  }

  const local = cellLocalPercent(index, inPlace.length);
  return {
    x: (col + local.x / 100) * (100 / cols),
    y: (row + local.y / 100) * (100 / rows),
  };
}

export function isNpcAgentId(agentId: string): boolean {
  return agentId !== PLAYER_AGENT_ID;
}
