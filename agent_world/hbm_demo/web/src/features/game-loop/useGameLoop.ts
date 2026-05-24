import { useCallback } from "react";
import {
  getActionResult,
  getSession,
  postPlayerTurn,
  resetSession,
  startSession,
} from "../../api/hbm";
import type { ActionResultCompleted, ActionResultProcessing } from "../../api/types";
import { POLL_TIMEOUT_MESSAGE } from "../../constants/runner";
import {
  MAX_POLL_ATTEMPTS,
  PLAYER_SENDER,
  POLL_INTERVAL_MS,
} from "../../constants/gameLoop";
import { useGameStoreContext } from "../../store/GameStoreProvider";
import { errorMessage, isRunnerNotReadyError } from "../../utils/apiError";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
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

/** F3-2 / F4-8 — start via session/start; full reset via session/reset. */
export function useStartGame() {
  const { applySessionStart, setLoading, dispatch } = useGameStoreContext();

  const beginSession = useCallback(
    async (mode: "start" | "reset") => {
      setLoading(true);
      dispatch({ type: "DISMISS_PHASE_TOAST" });
      dispatch({ type: "SET_ERROR", message: undefined });
      try {
        const response =
          mode === "reset" ? await resetSession() : await startSession();
        if (!response.data) {
          throw new Error(
            mode === "reset" ? "session/reset 未返回 data" : "session/start 未返回 data",
          );
        }
        applySessionStart(response.data);
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
        "确定要重开吗？将重置 Agent 世界、清空所有对话与进度，并从 Turn 1 重新开始。",
      )
    ) {
      return;
    }
    await beginSession("reset");
  }, [beginSession]);

  return { startGame, restartGame, resetDemo };
}

/** F3-3 + F5 + F11-C — incremental delta poll during processing. */
export function useGameLoop() {
  const { state, dispatch, setLoading } = useGameStoreContext();

  const refreshSession = useCallback(async () => {
    const response = await getSession();
    if (response.data?.initialized) {
      dispatch({ type: "APPLY_SESSION", data: response.data });
    }
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
      dispatch({ type: "SET_IMMEDIATE", message: undefined });
      dispatch({ type: "SET_ERROR", message: undefined });

      try {
        const response = await postPlayerTurn({ player_text: trimmed });
        const data = response.data;
        if (!data) {
          throw new Error("player-turn 未返回 data");
        }

        if (data.status === "game_over") {
          dispatch({ type: "SET_GAME_OVER", data });
          return;
        }

        if (data.status === "completed") {
          dispatch({ type: "SET_ENDING", data });
          return;
        }

        dispatch({ type: "SET_IMMEDIATE", message: data.immediate_msg });
        dispatch({
          type: "APPLY_PLAYER_TURN_PROCESSING",
          stats: data.stats_update,
          phase: data.current_phase,
          playerTurn: state.playerTurn + 1,
        });

        const taskId = data.task_id;
        const placeId = state.placeId;
        let sinceTick = data.start_tick ?? 0;
        let pollCompleted = false;

        for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
          if (attempt > 0) {
            await sleep(POLL_INTERVAL_MS);
          }

          const poll = await getActionResult(taskId, {
            place_id: placeId,
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
            dispatch({ type: "APPEND_TURN_DELTA", delta });
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
        dispatch({ type: "SET_IMMEDIATE", message: undefined });
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
    ],
  );

  return { sendTurn, refreshSession };
}
