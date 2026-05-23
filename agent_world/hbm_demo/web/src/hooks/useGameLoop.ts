import { useCallback } from "react";
import {
  getActionResult,
  getSession,
  postPlayerTurn,
  startSession,
} from "../api/hbm";
import { HbmApiError } from "../api/errors";
import type { ActionResultCompleted } from "../api/types";
import {
  MAX_POLL_ATTEMPTS,
  PLAYER_SENDER,
  POLL_INTERVAL_MS,
} from "../constants/gameLoop";
import { useGameStoreContext } from "../store/GameStoreProvider";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function isCompletedAction(
  data: unknown,
): data is ActionResultCompleted {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as ActionResultCompleted).status === "completed"
  );
}

/** F3-2 — start game via session/start. */
export function useStartGame() {
  const { applySessionStart, setLoading, dispatch } = useGameStoreContext();

  const startGame = useCallback(async () => {
    setLoading(true);
    try {
      const response = await startSession();
      if (!response.data) {
        throw new Error("session/start 未返回 data");
      }
      applySessionStart(response.data);
    } catch (err) {
      const message =
        err instanceof HbmApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "开始游戏失败";
      dispatch({ type: "SET_ERROR", message });
    } finally {
      setLoading(false);
    }
  }, [applySessionStart, dispatch, setLoading]);

  return { startGame };
}

/** F3-3 — dual-stage turn loop (PLAN2 appendix B). */
export function useGameLoop() {
  const { state, dispatch, setLoading } = useGameStoreContext();

  const refreshSession = useCallback(async () => {
    const response = await getSession();
    if (response.data?.initialized) {
      dispatch({ type: "APPLY_SESSION", data: response.data });
    }
  }, [dispatch]);

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

        for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
          await sleep(POLL_INTERVAL_MS);
          const poll = await getActionResult(taskId, { place_id: placeId });
          if (isCompletedAction(poll.data)) {
            dispatch({ type: "APPEND_ACTION_RESULT", data: poll.data });
            await refreshSession();
            break;
          }
        }
      } catch (err) {
        const message =
          err instanceof HbmApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "本回合处理失败";
        dispatch({ type: "SET_ERROR", message });
      } finally {
        setLoading(false);
        dispatch({ type: "SET_IMMEDIATE", message: undefined });
      }
    },
    [dispatch, refreshSession, setLoading, state.loading, state.placeId, state.playerTurn],
  );

  return { sendTurn, refreshSession };
}
