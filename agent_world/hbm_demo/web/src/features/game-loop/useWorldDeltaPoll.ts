import { useEffect, useRef } from "react";
import { getWorldDelta } from "../../api/hbm";
import {
  DELTA_POLL_MS,
  DELTA_POLL_PAUSED_MS,
} from "../../constants/gameLoop";
import { useGameStoreContext } from "../../store/GameStoreProvider";
import { errorMessage, isRunnerNotReadyError } from "../../utils/apiError";
import { applyWorldDeltaPayload } from "./worldDeltaApply";

/** F14 — HTTP poll fallback when WebSocket unavailable (dev_logs/31 Phase 2/5). */
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
        sinceTickRef.current = applyWorldDeltaPayload(
          dispatch,
          data,
          sinceTickRef.current,
        );
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
