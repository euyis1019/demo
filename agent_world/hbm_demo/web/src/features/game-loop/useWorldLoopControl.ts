import { useCallback, useEffect } from "react";
import {
  getWorldLoopStatus,
  pauseWorldLoop,
  resumeWorldLoop,
} from "../../api/hbm";
import type { WorldLoopState } from "../../api/types";
import { useGameStoreContext } from "../../store/GameStoreProvider";
import { errorMessage, isRunnerNotReadyError } from "../../utils/apiError";

const WORLD_LOOP_POLL_MS = 1000;

function normalizeLoopState(raw: string | undefined): WorldLoopState {
  if (
    raw === "running" ||
    raw === "paused" ||
    raw === "stopped" ||
    raw === "disabled"
  ) {
    return raw;
  }
  return "unknown";
}

/** F13 — poll world-loop status + pause/resume controls. */
export function useWorldLoopControl(enabled: boolean) {
  const { state, dispatch } = useGameStoreContext();

  const applyStatus = useCallback(
    (data: {
      loop_state?: string;
      current_tick?: number;
      paused_at_tick?: number | null;
    }) => {
      dispatch({
        type: "SET_WORLD_LOOP_STATUS",
        loopState: normalizeLoopState(data.loop_state),
        currentTick:
          typeof data.current_tick === "number" ? data.current_tick : undefined,
        pausedAtTick:
          typeof data.paused_at_tick === "number" ? data.paused_at_tick : undefined,
      });
    },
    [dispatch],
  );

  const refreshStatus = useCallback(async () => {
    try {
      const response = await getWorldLoopStatus();
      if (response.data) {
        applyStatus(response.data);
      }
    } catch {
      /* keep last known loop state */
    }
  }, [applyStatus]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    void refreshStatus();
    const timer = setInterval(() => void refreshStatus(), WORLD_LOOP_POLL_MS);
    return () => clearInterval(timer);
  }, [enabled, refreshStatus]);

  const pauseWorld = useCallback(async () => {
    try {
      const response = await pauseWorldLoop();
      if (response.data) {
        applyStatus(response.data);
      }
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        message: errorMessage(err, "暂停世界失败"),
      });
      if (isRunnerNotReadyError(err)) {
        dispatch({ type: "SET_RUNNER_MODAL", open: true });
      }
    }
  }, [applyStatus, dispatch]);

  const resumeWorld = useCallback(async () => {
    try {
      const response = await resumeWorldLoop();
      if (response.data) {
        applyStatus(response.data);
      }
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        message: errorMessage(err, "继续世界失败"),
      });
      if (isRunnerNotReadyError(err)) {
        dispatch({ type: "SET_RUNNER_MODAL", open: true });
      }
    }
  }, [applyStatus, dispatch]);

  const pauseDisabled =
    !enabled ||
    state.loading ||
    state.view !== "playing" ||
    state.worldLoopState === "disabled";

  return {
    worldLoopState: state.worldLoopState,
    worldLoopPausedAtTick: state.worldLoopPausedAtTick,
    pauseDisabled,
    pauseWorld,
    resumeWorld,
    refreshStatus,
  };
}
