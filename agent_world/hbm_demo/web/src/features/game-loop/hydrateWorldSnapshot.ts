import type { Dispatch } from "react";
import { getWorldSnapshot } from "../../api/hbm";
import type { GameAction } from "../../store/gameStore";

/** Load full world read-model (F12 snapshot + F14 delta since tick 0). */
export async function hydrateWorldFromServer(
  dispatch: Dispatch<GameAction>,
): Promise<void> {
  const snapResp = await getWorldSnapshot();
  if (snapResp.data) {
    dispatch({ type: "SET_WORLD_SNAPSHOT", snapshot: snapResp.data });
    dispatch({
      type: "WORLD_SYNC_READY",
      deltaSinceTick: snapResp.data.through_tick ?? 0,
    });
  } else {
    dispatch({ type: "WORLD_SYNC_READY", deltaSinceTick: 0 });
  }
}
