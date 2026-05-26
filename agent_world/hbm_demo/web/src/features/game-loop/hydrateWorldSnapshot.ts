import type { Dispatch } from "react";
import { getSession, getWorldSnapshot } from "../../api/hbm";
import type { GameAction } from "../../store/gameStore";

/** Poll cursor for replaying agent lines since this Flask session began. */
export function deltaSinceTickForSession(startTick: number): number {
  const start = Math.max(0, Number(startTick) || 0);
  // RDC delta uses attempted_at > since_tick; F2F uses >=. Back up one tick.
  return start > 0 ? start - 1 : 0;
}

/** Load full world read-model (F12 snapshot + F14 delta replay from session start). */
export async function hydrateWorldFromServer(
  dispatch: Dispatch<GameAction>,
  options?: { startTick?: number },
): Promise<void> {
  const snapResp = await getWorldSnapshot();
  let startTick = options?.startTick;
  if (startTick == null) {
    const sessionResp = await getSession();
    startTick = sessionResp.data?.initialized
      ? Number(sessionResp.data.start_tick ?? 0)
      : 0;
  }
  const deltaSinceTick = deltaSinceTickForSession(startTick ?? 0);

  if (snapResp.data) {
    dispatch({ type: "SET_WORLD_SNAPSHOT", snapshot: snapResp.data });
    dispatch({ type: "WORLD_SYNC_READY", deltaSinceTick });
  } else {
    dispatch({ type: "WORLD_SYNC_READY", deltaSinceTick: 0 });
  }
}
