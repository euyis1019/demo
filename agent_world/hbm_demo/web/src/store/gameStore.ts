import type {
  ActionResultCompleted,
  GameMessage,
  PlayerTurnCompleted,
  PlayerTurnGameOver,
  SessionSnapshot,
  SessionStartData,
  Stats,
} from "../api/types";
import { MAX_TURNS } from "../constants/gameLoop";

export type EndingId = PlayerTurnCompleted["ending_id"];
export type GameView = "boot" | "playing" | "game_over" | "ending";

export interface GameState {
  view: GameView;
  healthChecking: boolean;
  runnerReady: boolean;
  healthError?: string;
  sessionInitialized: boolean;
  loading: boolean;
  immediateMsg?: string;
  stats: Stats;
  phase: string;
  playerTurn: number;
  placeId: string;
  f2fMessages: GameMessage[];
  rdcMessages: GameMessage[];
  grpMessages: GameMessage[];
  endingId?: EndingId;
  lastError?: string;
}

export const INITIAL_STATS: Stats = {
  vision: 0,
  execution: 0,
  trust: 10,
  burnout: 0,
};

export function createInitialState(): GameState {
  return {
    view: "boot",
    healthChecking: true,
    runnerReady: false,
    sessionInitialized: false,
    loading: false,
    stats: { ...INITIAL_STATS },
    phase: "Phase 1",
    playerTurn: 1,
    placeId: "nvidia_reception",
    f2fMessages: [],
    rdcMessages: [],
    grpMessages: [],
  };
}

export type GameAction =
  | { type: "HEALTH_CHECK_START" }
  | { type: "HEALTH_CHECK_DONE"; ready: boolean; error?: string }
  | { type: "START_SESSION"; data: SessionStartData }
  | { type: "APPLY_SESSION"; data: SessionSnapshot }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_IMMEDIATE"; message?: string }
  | { type: "APPLY_PLAYER_TURN_PROCESSING"; stats: Stats; phase: string; playerTurn: number }
  | { type: "PUSH_PLAYER_BUBBLE"; message: GameMessage }
  | { type: "APPEND_ACTION_RESULT"; data: ActionResultCompleted }
  | { type: "SET_GAME_OVER"; data: PlayerTurnGameOver }
  | { type: "SET_ENDING"; data: PlayerTurnCompleted }
  | { type: "SET_ERROR"; message?: string }
  | { type: "RESET_PLAYTHROUGH" };

function statsFromSnapshot(data: SessionSnapshot | SessionStartData): Stats {
  return { ...(data.stats ?? INITIAL_STATS) };
}

export function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case "HEALTH_CHECK_START":
      return { ...state, healthChecking: true, healthError: undefined };
    case "HEALTH_CHECK_DONE":
      return {
        ...state,
        healthChecking: false,
        runnerReady: action.ready,
        healthError: action.error,
      };
    case "START_SESSION":
      return {
        ...state,
        view: "playing",
        sessionInitialized: true,
        stats: statsFromSnapshot(action.data),
        phase: action.data.phase,
        playerTurn: action.data.player_turn,
        placeId: action.data.place_id,
        f2fMessages: [],
        rdcMessages: [],
        grpMessages: [],
        immediateMsg: undefined,
        endingId: undefined,
        lastError: undefined,
      };
    case "APPLY_SESSION":
      if (!action.data.initialized) {
        return { ...state, sessionInitialized: false, view: "boot" };
      }
      return {
        ...state,
        view: state.view === "game_over" || state.view === "ending" ? state.view : "playing",
        sessionInitialized: true,
        stats: statsFromSnapshot(action.data),
        phase: action.data.phase ?? action.data.current_phase ?? state.phase,
        playerTurn: action.data.player_turn ?? state.playerTurn,
        placeId: action.data.place_id ?? state.placeId,
      };
    case "SET_LOADING":
      return { ...state, loading: action.loading };
    case "SET_IMMEDIATE":
      return { ...state, immediateMsg: action.message };
    case "APPLY_PLAYER_TURN_PROCESSING":
      return {
        ...state,
        stats: { ...action.stats },
        phase: action.phase,
        playerTurn: action.playerTurn,
      };
    case "PUSH_PLAYER_BUBBLE":
      return {
        ...state,
        f2fMessages: [...state.f2fMessages, action.message],
      };
    case "APPEND_ACTION_RESULT":
      return {
        ...state,
        stats: { ...action.data.stats_update },
        phase: action.data.current_phase,
        immediateMsg: undefined,
        f2fMessages: mergeMessages(state.f2fMessages, action.data.public_messages),
        rdcMessages: mergeMessages(state.rdcMessages, action.data.observer_messages),
        grpMessages: mergeMessages(state.grpMessages, action.data.group_messages),
      };
    case "SET_GAME_OVER":
      return {
        ...state,
        view: "game_over",
        loading: false,
        immediateMsg: undefined,
        stats: { ...action.data.stats_update },
        phase: action.data.current_phase,
        f2fMessages: mergeMessages(state.f2fMessages, action.data.public_messages),
      };
    case "SET_ENDING":
      return {
        ...state,
        view: "ending",
        loading: false,
        immediateMsg: undefined,
        stats: { ...action.data.stats_update },
        phase: action.data.current_phase,
        endingId: action.data.ending_id,
      };
    case "SET_ERROR":
      return { ...state, lastError: action.message, loading: false };
    case "RESET_PLAYTHROUGH":
      return {
        ...createInitialState(),
        healthChecking: false,
        runnerReady: state.runnerReady,
      };
    default:
      return state;
  }
}

export function mergeMessages(
  existing: GameMessage[],
  incoming: GameMessage[] | undefined,
): GameMessage[] {
  if (!incoming?.length) {
    return existing;
  }
  const seen = new Set(existing.map(messageKey));
  const merged = [...existing];
  for (const message of incoming) {
    const key = messageKey(message);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(message);
  }
  return merged.sort(
    (a, b) => (a.attempted_at ?? 0) - (b.attempted_at ?? 0),
  );
}

function messageKey(message: GameMessage): string {
  return [
    message.type,
    message.sender,
    message.recipient ?? "",
    message.group_id ?? "",
    message.attempted_at ?? "",
    message.content,
  ].join("|");
}

export { MAX_TURNS };
