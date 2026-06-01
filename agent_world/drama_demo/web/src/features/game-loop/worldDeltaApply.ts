import type { Dispatch } from "react";
import type { WorldDeltaData } from "../../api/types";
import type { GameAction } from "../../store/gameStore";

function hasDeltaActivity(data: Partial<WorldDeltaData>): boolean {
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
    (data.state_changes?.length ?? 0) > 0 ||
    (data.social_events?.length ?? 0) > 0 ||
    (data.world_events?.length ?? 0) > 0
  );
}

function loopSettled(loopState: string | undefined): boolean {
  return (
    loopState === undefined ||
    loopState === "paused" ||
    loopState === "stopped" ||
    loopState === "unknown"
  );
}

/** Advance poll cursor — avoid skipping in-flight ticks while loop is running. */
export function computeNextSinceTick(
  data: Pick<WorldDeltaData, "through_tick" | "loop_state"> & Partial<WorldDeltaData>,
  sinceTick: number,
): number {
  const through = data.through_tick;
  if (hasDeltaActivity(data)) {
    if (loopSettled(data.loop_state)) {
      return Math.max(sinceTick, through);
    }
    // Player F2F and NPC reply often share the same engine tick; keep re-reading it.
    return Math.max(sinceTick, Math.max(0, through - 1));
  }
  if (through > sinceTick && loopSettled(data.loop_state)) {
    return through;
  }
  return sinceTick;
}

/** Shared delta apply logic for F14 poll and F16 WebSocket. */
export function applyWorldDeltaPayload(
  dispatch: Dispatch<GameAction>,
  data: WorldDeltaData,
  sinceTick: number,
): number {
  const through = data.through_tick;
  const nextSince = computeNextSinceTick(data, sinceTick);

  if (through > sinceTick || hasDeltaActivity(data)) {
    dispatch({ type: "APPLY_WORLD_DELTA", delta: data, nextSinceTick: nextSince });
  } else if (nextSince > sinceTick) {
    dispatch({ type: "SET_DELTA_SINCE", nextSinceTick: nextSince });
  }

  if (data.game_over) {
    // bad_reject → GameOverScreen; offer-driven Phase-4 finale → EndingScreen.
    if (data.game_over.status === "completed") {
      dispatch({ type: "SET_ENDING", data: data.game_over });
    } else {
      dispatch({ type: "SET_GAME_OVER", data: data.game_over });
    }
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

  return nextSince;
}
