import type { Dispatch } from "react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import type { SessionSnapshot, SessionStartData } from "../api/types";
import {
  createInitialState,
  gameReducer,
  type GameAction,
  type GameState,
} from "./gameStore";

interface GameStoreContextValue {
  state: GameState;
  dispatch: Dispatch<GameAction>;
  applySessionStart: (data: SessionStartData) => void;
  applySessionSnapshot: (data: SessionSnapshot) => void;
  setHealthChecking: () => void;
  setHealthResult: (ready: boolean, error?: string) => void;
  setLoading: (loading: boolean) => void;
  resetPlaythrough: () => void;
}

const GameStoreContext = createContext<GameStoreContextValue | null>(null);

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

export function useGameStoreContext(): GameStoreContextValue {
  const ctx = useContext(GameStoreContext);
  if (!ctx) {
    throw new Error("useGameStoreContext must be used within GameStoreProvider");
  }
  return ctx;
}
