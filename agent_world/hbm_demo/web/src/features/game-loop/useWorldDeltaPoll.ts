import { useCallback, useEffect, useRef } from "react";
import { getWorldDelta } from "../../api/hbm";
import {
  DELTA_POLL_MS,
  DELTA_POLL_PAUSED_MS,
} from "../../constants/gameLoop";
import { useGameStoreContext } from "../../store/GameStoreProvider";
import { errorMessage, isRunnerNotReadyError } from "../../utils/apiError";
import { applyWorldDeltaPayload } from "./worldDeltaApply";

/**
 * F14 — HTTP poll for session world delta.
 * Also re-fetches immediately when backend env tick advances (tick-triggered sync).
 */
export function useWorldDeltaPoll(
  enabled: boolean,
  paused: boolean,
  envTick: number | null = null,
): void {
  const { state, dispatch } = useGameStoreContext();
  const sinceTickRef = useRef(state.worldTick);
  const inFlightRef = useRef(false);
  const lastEnvTickRef = useRef<number | null>(null);

  useEffect(() => {
    sinceTickRef.current = state.worldTick;
  }, [state.worldTick]);

  const poll = useCallback(async () => {
    if (inFlightRef.current) {
      return;
    }
    inFlightRef.current = true;
    try {
      const response = await getWorldDelta(sinceTickRef.current);
      const data = response.data;
      if (!data) {
        return;
      }
      sinceTickRef.current = applyWorldDeltaPayload(
        dispatch,
        data,
        sinceTickRef.current,
      );
    } catch (err) {
      if (isRunnerNotReadyError(err)) {
        return;
      }
      dispatch({
        type: "SET_ERROR",
        message: errorMessage(err, "世界同步失败"),
      });
    } finally {
      inFlightRef.current = false;
    }
  }, [dispatch]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    void poll();
    const intervalMs = paused ? DELTA_POLL_PAUSED_MS : DELTA_POLL_MS;
    const timer = window.setInterval(() => {
      void poll();
    }, intervalMs);

    return () => {
      window.clearInterval(timer);
    };
  }, [enabled, paused, poll]);

  /** Backend tick advanced → pull delta immediately (don't wait for next interval). */
  useEffect(() => {
    if (!enabled || envTick == null) {
      return;
    }
    const prev = lastEnvTickRef.current;
    lastEnvTickRef.current = envTick;
    if (prev !== null && envTick > prev) {
      void poll();
    }
  }, [enabled, envTick, poll]);
}
