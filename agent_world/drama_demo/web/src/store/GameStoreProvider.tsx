import {
  useCallback,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import type { SessionSnapshot, SessionStartData } from "../api/types";
import { createInitialState, gameReducer } from "./gameStore";
import { GameStoreContext } from "./gameStoreContext";

export function GameStoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(gameReducer, undefined, createInitialState);

  const applySessionStart = useCallback((data: SessionStartData) => {
    dispatch({ type: "START_SESSION", data });
  }, []);

  const applySessionSnapshot = useCallback((data: SessionSnapshot) => {
    dispatch({ type: "APPLY_SESSION", data });
  }, []);

  const setHealthChecking = useCallback(() => {
    dispatch({ type: "HEALTH_CHECK_START" });
  }, []);

  const setHealthResult = useCallback((ready: boolean, error?: string) => {
    dispatch({ type: "HEALTH_CHECK_DONE", ready, error });
  }, []);

  const setLoading = useCallback((loading: boolean) => {
    dispatch({ type: "SET_LOADING", loading });
  }, []);

  const resetPlaythrough = useCallback(() => {
    dispatch({ type: "RESET_PLAYTHROUGH" });
  }, []);

  const value = useMemo(
    () => ({
      state,
      dispatch,
      applySessionStart,
      applySessionSnapshot,
      setHealthChecking,
      setHealthResult,
      setLoading,
      resetPlaythrough,
    }),
    [
      state,
      applySessionStart,
      applySessionSnapshot,
      setHealthChecking,
      setHealthResult,
      setLoading,
      resetPlaythrough,
    ],
  );

  return (
    <GameStoreContext.Provider value={value}>{children}</GameStoreContext.Provider>
  );
}
