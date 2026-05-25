import { useEffect, useRef } from "react";
import { getWorldDelta } from "../../api/hbm";
import type { WorldDeltaData } from "../../api/types";
import {
  DELTA_POLL_MS,
  DELTA_POLL_PAUSED_MS,
} from "../../constants/gameLoop";
import { useGameStoreContext } from "../../store/GameStoreProvider";
import { errorMessage, isRunnerNotReadyError } from "../../utils/apiError";

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

/** F14 — resident session delta poll, decoupled from sendTurn (dev_logs/31 Phase 2). */
export function useWorldDeltaPoll(enabled: boolean, paused: boolean): void {
  const { state, dispatch } = useGameStoreContext();
  const sinceTickRef = useRef(state.worldTick);
  const inFlightRef = useRef(false);

  useEffect(() => {
    sinceTickRef.current = state.worldTick;
  }, [state.worldTick]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let cancelled = false;
    const intervalMs = paused ? DELTA_POLL_PAUSED_MS : DELTA_POLL_MS;

    const poll = async () => {
      if (cancelled || inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      try {
        const response = await getWorldDelta(sinceTickRef.current);
        const data = response.data;
        if (!data || cancelled) {
          return;
        }

        const through = data.through_tick;
        if (through > sinceTickRef.current || hasDeltaActivity(data)) {
          dispatch({ type: "APPLY_WORLD_DELTA", delta: data });
          sinceTickRef.current = through;
        }

        if (data.game_over?.status === "game_over") {
          dispatch({ type: "SET_GAME_OVER", data: data.game_over });
          return;
        }

        if (data.stats_update && data.current_phase && data.player_turn !== undefined) {
          dispatch({
            type: "APPLY_PLAYER_TURN_PROCESSING",
            stats: data.stats_update,
            phase: data.current_phase,
            playerTurn: data.player_turn,
          });
        }
      } catch (err) {
        if (cancelled || isRunnerNotReadyError(err)) {
          return;
        }
        dispatch({
          type: "SET_ERROR",
          message: errorMessage(err, "世界同步失败"),
        });
      } finally {
        inFlightRef.current = false;
      }
    };

    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, intervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [dispatch, enabled, paused]);
}
