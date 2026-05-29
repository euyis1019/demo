import type { CSSProperties } from "react";
import { PLAYER_AGENT_ID } from "../../../constants/agents";
import { ROOM_GRID, type PlaceId } from "../../../utils/places";
import { agentsInPlace } from "../../../store/worldSync";

const PLACE_GRID_CELL: Record<PlaceId, { col: number; row: number }> = {
  nvidia_reception: { col: 0, row: 0 },
  jensen_private_room: { col: 1, row: 0 },
  negotiation_room: { col: 0, row: 1 },
  openai_hq: { col: 1, row: 1 },
};

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

/** Map agent id → center point on the 2×2 room grid (0–100). */
export function agentGridCenter(
  agentId: string,
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>,
): { x: number; y: number } | null {
  const loc = agentLocations[agentId];
  if (!loc) {
    return null;
  }
  const placeId = loc.placeId as PlaceId;
  const cell = PLACE_GRID_CELL[placeId];
  if (!cell) {
    return null;
  }

  const inPlace = agentsInPlace(agentLocations, placeId);
  const index = inPlace.indexOf(agentId);
  if (index < 0) {
    return null;
  }

  const local = cellLocalPercent(index, inPlace.length);
  return {
    x: cell.col * 50 + (local.x / 100) * 50,
    y: cell.row * 50 + (local.y / 100) * 50,
  };
}

export function isNpcAgentId(agentId: string): boolean {
  return agentId !== PLAYER_AGENT_ID;
}

export { ROOM_GRID };
