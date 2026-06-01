import { createContext, useContext, type Dispatch } from "react";
import type { SessionSnapshot, SessionStartData } from "../api/types";
import type { GameAction, GameState } from "./gameStore";

export interface GameStoreContextValue {
  state: GameState;
  dispatch: Dispatch<GameAction>;
  applySessionStart: (data: SessionStartData) => void;
  applySessionSnapshot: (data: SessionSnapshot) => void;
  setHealthChecking: () => void;
  setHealthResult: (ready: boolean, error?: string) => void;
  setLoading: (loading: boolean) => void;
  resetPlaythrough: () => void;
}

export const GameStoreContext = createContext<GameStoreContextValue | null>(null);

export function useGameStoreContext(): GameStoreContextValue {
  const ctx = useContext(GameStoreContext);
  if (!ctx) {
    throw new Error("useGameStoreContext must be used within GameStoreProvider");
  }
  return ctx;
}
