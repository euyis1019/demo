import { useCallback, useEffect, useRef } from "react";
import {
  getActionResult,
  getSession,
  postPlayerTurn,
  resetSession,
  resumeWorldLoop,
  startSession,
} from "../../api/hbm";
import { syncWorldDeltaCatchUp } from "./syncWorldDelta";
import { hydrateWorldFromServer } from "./hydrateWorldSnapshot";
import { computeNextSinceTick } from "./worldDeltaApply";
import type {
  ActionResultCompleted,
  ActionResultProcessing,
  PlayerTurnAccepted,
  PlayerTurnProcessing,
} from "../../api/types";
import { POLL_TIMEOUT_MESSAGE } from "../../constants/runner";
import {
  MAX_POLL_ATTEMPTS,
  PLAYER_SENDER,
  POLL_INTERVAL_MS,
} from "../../constants/gameLoop";
import { useGameStoreContext } from "../../store/GameStoreProvider";
import { errorMessage, isRunnerNotReadyError } from "../../utils/apiError";
import { hardReloadPage } from "../../utils/hardReload";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function isAcceptedTurn(data: unknown): data is PlayerTurnAccepted {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as PlayerTurnAccepted).accepted === true
  );
}

function isCompletedAction(data: unknown): data is ActionResultCompleted {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as ActionResultCompleted).status === "completed"
  );
}

function isProcessingWithDelta(
  data: unknown,
): data is ActionResultProcessing & { delta: NonNullable<ActionResultProcessing["delta"]> } {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as ActionResultProcessing).status === "processing" &&
    (data as ActionResultProcessing).delta !== undefined
  );
}

/** Hydrate full world state from snapshot (includes delta payload since tick 0). */
export { hydrateWorldFromServer } from "./hydrateWorldSnapshot";

/** F3-2 / F4-8 — start via session/start; full reset via session/reset. */
export function useStartGame() {
  const { applySessionStart, setLoading, dispatch } = useGameStoreContext();

  const beginSession = useCallback(
    async (mode: "start" | "reset") => {
      setLoading(true);
      dispatch({ type: "DISMISS_PHASE_TOAST" });
      dispatch({ type: "SET_ERROR", message: undefined });
      try {
        if (mode === "reset") {
          const response = await resetSession();
          if (!response.data) {
            throw new Error("session/reset 未返回 data");
          }
          hardReloadPage();
          return;
        }

        const response = await startSession();
        if (!response.data) {
          throw new Error("session/start 未返回 data");
        }
        applySessionStart(response.data);
        await hydrateWorldFromServer(dispatch, {
          startTick: response.data.start_tick,
        });
      } catch (err) {
        dispatch({
          type: "SET_ERROR",
          message: errorMessage(
            err,
            mode === "reset" ? "重开失败" : "开始游戏失败",
          ),
        });
        if (isRunnerNotReadyError(err)) {
          dispatch({ type: "SET_RUNNER_MODAL", open: true });
        }
      } finally {
        setLoading(false);
      }
    },
    [applySessionStart, dispatch, setLoading],
  );

  const startGame = useCallback(async () => {
    await beginSession("start");
  }, [beginSession]);

  const restartGame = useCallback(async () => {
    await beginSession("reset");
  }, [beginSession]);

  const resetDemo = useCallback(async () => {
    if (
      !window.confirm(
        "确定要重开吗？将重置 Agent 世界、清空所有对话与进度，并从 Turn 1 重新开始（页面将自动刷新）。",
      )
    ) {
      return;
    }
    await beginSession("reset");
  }, [beginSession]);

  return { startGame, restartGame, resetDemo };
}

/** F3-3 + Phase 2 — POST enqueue only; F14 poll merges world delta. */
export function useGameLoop() {
  const { state, dispatch, setLoading } = useGameStoreContext();
  const deltaSinceRef = useRef(state.deltaSinceTick);

  useEffect(() => {
    deltaSinceRef.current = state.deltaSinceTick;
  }, [state.deltaSinceTick]);

  const refreshSession = useCallback(async () => {
    const response = await getSession();
    if (response.data?.initialized) {
      dispatch({ type: "APPLY_SESSION", data: response.data });
    }
    await hydrateWorldFromServer(dispatch);
  }, [dispatch]);

  const handleApiError = useCallback(
    (err: unknown, fallback: string) => {
      dispatch({ type: "SET_ERROR", message: errorMessage(err, fallback) });
      if (isRunnerNotReadyError(err)) {
        dispatch({ type: "SET_RUNNER_MODAL", open: true });
      }
    },
    [dispatch],
  );

  const sendTurn = useCallback(
    async (playerText: string) => {
      const trimmed = playerText.trim();
      if (!trimmed || state.loading) {
        return;
      }

      setLoading(true);
      dispatch({
        type: "PUSH_PLAYER_BUBBLE",
        message: {
          sender: PLAYER_SENDER,
          content: trimmed,
          type: "F2F",
          place_id: state.placeId,
        },
      });
      dispatch({ type: "SET_ERROR", message: undefined });

      try {
        if (state.worldLoopState === "paused") {
          await resumeWorldLoop();
        }

        const response = await postPlayerTurn({ player_text: trimmed });
        const data = response.data;
        if (!data) {
          throw new Error("player-turn 未返回 data");
        }

        if ("status" in data && data.status === "game_over") {
          dispatch({ type: "SET_GAME_OVER", data });
          return;
        }

        if ("status" in data && data.status === "completed") {
          dispatch({ type: "SET_ENDING", data });
          return;
        }

        if (isAcceptedTurn(data)) {
          dispatch({
            type: "APPLY_PLAYER_TURN_PROCESSING",
            stats: data.stats_update,
            phase: data.current_phase,
            playerTurn: data.player_turn,
          });
          try {
            await syncWorldDeltaCatchUp(dispatch, deltaSinceRef.current);
          } catch (err) {
            handleApiError(err, "世界同步失败");
          }
          return;
        }

        // Legacy F11 path when world loop disabled.
        const legacy = data as PlayerTurnProcessing;
        dispatch({
          type: "APPLY_PLAYER_TURN_PROCESSING",
          stats: legacy.stats_update,
          phase: legacy.current_phase,
          playerTurn: state.playerTurn + 1,
        });

        const taskId = legacy.task_id;
        let sinceTick = legacy.start_tick ?? 0;
        let pollCompleted = false;

        for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
          if (attempt > 0) {
            await sleep(POLL_INTERVAL_MS);
          }

          const poll = await getActionResult(taskId, {
            place_id: state.placeId,
            since_tick: sinceTick,
          });
          const pollData = poll.data;

          if (pollData?.status === "game_over") {
            pollCompleted = true;
            dispatch({ type: "SET_GAME_OVER", data: pollData });
            break;
          }

          if (pollData?.status === "error") {
            dispatch({
              type: "SET_ERROR",
              message: pollData.error ?? "后台 inject 失败",
            });
            break;
          }

          if (isProcessingWithDelta(pollData)) {
            const { delta } = pollData;
            dispatch({
              type: "APPLY_WORLD_DELTA",
              delta,
              nextSinceTick: computeNextSinceTick(delta, sinceTick),
            });
            sinceTick = delta.through_tick;
          }

          if (isCompletedAction(pollData)) {
            pollCompleted = true;
            dispatch({ type: "APPEND_ACTION_RESULT", data: pollData });
            await refreshSession();
            break;
          }
        }

        if (!pollCompleted) {
          dispatch({ type: "SET_ERROR", message: POLL_TIMEOUT_MESSAGE });
        }
      } catch (err) {
        handleApiError(err, "本回合处理失败");
      } finally {
        setLoading(false);
      }
    },
    [
      dispatch,
      handleApiError,
      refreshSession,
      setLoading,
      state.loading,
      state.placeId,
      state.playerTurn,
      state.worldLoopState,
    ],
  );

  return { sendTurn, refreshSession };
}
