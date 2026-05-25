import type { Dispatch } from "react";
import type { WorldDeltaData } from "../../api/types";
import type { GameAction } from "../../store/gameStore";

function hasDeltaActivity(data: WorldDeltaData): boolean {
  const roomF2f = data.room_f2f ?? {};
  const hasF2f = Object.values(roomF2f).some(
    (messages) => (messages?.length ?? 0) > 0,
  );
  const hasAgentMsgs = Object.values(data.agent_messages ?? {}).some(
    (bucket) => (bucket.rdc?.length ?? 0) > 0 || (bucket.grp?.length ?? 0) > 0,
  );
  return (
    hasF2f ||
    hasAgentMsgs ||
    (data.observer_messages?.length ?? 0) > 0 ||
    (data.group_messages?.length ?? 0) > 0 ||
    (data.location_changes?.length ?? 0) > 0 ||
    (data.world_events?.length ?? 0) > 0
  );
}

/** Shared delta apply logic for F14 poll and F16 WebSocket. */
export function applyWorldDeltaPayload(
  dispatch: Dispatch<GameAction>,
  data: WorldDeltaData,
  sinceTick: number,
): number {
  const through = data.through_tick;
  if (through > sinceTick || hasDeltaActivity(data)) {
    dispatch({ type: "APPLY_WORLD_DELTA", delta: data });
  }

  if (data.game_over?.status === "game_over") {
    dispatch({ type: "SET_GAME_OVER", data: data.game_over });
    return through;
  }

  if (data.stats_update && data.current_phase && data.player_turn !== undefined) {
    dispatch({
      type: "APPLY_PLAYER_TURN_PROCESSING",
      stats: data.stats_update,
      phase: data.current_phase,
      playerTurn: data.player_turn,
    });
  }

  return through > sinceTick ? through : sinceTick;
}
