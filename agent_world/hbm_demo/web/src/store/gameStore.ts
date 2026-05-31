import type {
  ActionResultCompleted,
  GameMessage,
  PlayerTurnCompleted,
  PlayerTurnGameOver,
  SessionSnapshot,
  SessionStartData,
  Stats,
  TurnDelta,
  WorldLoopState,
  WorldSnapshot,
} from "../api/types";
import { getPhaseTransitionMessage } from "../constants/phaseTransitions";
import { MAX_TURNS } from "../constants/gameLoop";
import type { PlaceId } from "../utils/places";
import { emptyRoomF2f } from "../utils/places";
import {
  applyWorldDelta,
  applyWorldSnapshot,
  extractRdcLinks,
  pushPlayerBubbleToRoom,
  type AgentInbox,
  type RdcLink,
} from "./worldSync";
import type { WorldEvent } from "../api/types";

export type EndingId = PlayerTurnCompleted["ending_id"];
export type GameView = "select" | "boot" | "playing" | "game_over" | "ending";

export interface GameState {
  view: GameView;
  healthChecking: boolean;
  runnerReady: boolean;
  healthError?: string;
  sessionInitialized: boolean;
  loading: boolean;
  phaseToast?: string | null;
  stats: Stats;
  phase: string;
  playerTurn: number;
  placeId: string;
  /** Display / env tick — not used as delta poll cursor. */
  worldTick: number;
  /** Exclusive lower bound for GET /world-delta since_tick. */
  deltaSinceTick: number;
  /** True after initial snapshot hydrate — avoids racing poll during startup. */
  worldSyncReady: boolean;
  worldLoopState: WorldLoopState;
  worldLoopPausedAtTick?: number;
  nameMap: Record<string, string>;
  roomF2f: Record<PlaceId, GameMessage[]>;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  agentInbox: Record<string, AgentInbox>;
  /** 每个 agent 最新情绪标签（驱动剧情立绘切换）。 */
  agentMood: Record<string, string>;
  worldEvents: WorldEvent[];
  pendingWorldEvent: WorldEvent | null;
  processedWorldEventIds: string[];
  activeAgentModal: string | null;
  recentMoveKeys: string[];
  recentRdcLinks: RdcLink[];
  endingId?: EndingId;
  lastError?: string;
  runnerModalOpen: boolean;
}

export const INITIAL_STATS: Stats = {
  vision: 0,
  execution: 0,
  trust: 10,
  burnout: 0,
};

export function createInitialState(): GameState {
  return {
    view: "select",
    healthChecking: true,
    runnerReady: false,
    sessionInitialized: false,
    loading: false,
    phaseToast: null,
    stats: { ...INITIAL_STATS },
    phase: "Phase 1",
    playerTurn: 1,
    placeId: "nvidia_reception",
    worldTick: 0,
    deltaSinceTick: 0,
    worldSyncReady: false,
    worldLoopState: "unknown",
    nameMap: {},
    roomF2f: emptyRoomF2f(),
    agentLocations: {},
    agentInbox: {},
    agentMood: {},
    worldEvents: [],
    pendingWorldEvent: null,
    processedWorldEventIds: [],
    activeAgentModal: null,
    recentMoveKeys: [],
    recentRdcLinks: [],
    runnerModalOpen: false,
  };
}

export type GameAction =
  | { type: "ENTER_BOOT" }
  | { type: "HEALTH_CHECK_START" }
  | { type: "HEALTH_CHECK_DONE"; ready: boolean; error?: string }
  | { type: "START_SESSION"; data: SessionStartData }
  | { type: "APPLY_SESSION"; data: SessionSnapshot }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "APPLY_PLAYER_TURN_PROCESSING"; stats: Stats; phase: string; playerTurn: number }
  | { type: "PUSH_PLAYER_BUBBLE"; message: GameMessage }
  | { type: "APPEND_TURN_DELTA"; delta: TurnDelta }
  | { type: "APPLY_WORLD_DELTA"; delta: TurnDelta; nextSinceTick: number }
  | { type: "SET_DELTA_SINCE"; nextSinceTick: number }
  | { type: "WORLD_SYNC_READY"; deltaSinceTick: number }
  | { type: "APPEND_ACTION_RESULT"; data: ActionResultCompleted }
  | { type: "SET_GAME_OVER"; data: PlayerTurnGameOver }
  | { type: "SET_ENDING"; data: PlayerTurnCompleted }
  | { type: "SET_ERROR"; message?: string }
  | { type: "SET_RUNNER_MODAL"; open: boolean }
  | { type: "DISMISS_PHASE_TOAST" }
  | { type: "RESET_PLAYTHROUGH" }
  | { type: "SET_WORLD_SNAPSHOT"; snapshot: WorldSnapshot }
  | {
      type: "SET_WORLD_LOOP_STATUS";
      loopState: WorldLoopState;
      currentTick?: number;
      pausedAtTick?: number;
    }
  | { type: "OPEN_AGENT_MODAL"; agentId: string }
  | { type: "CLOSE_AGENT_MODAL" }
  | { type: "DISMISS_WORLD_EVENT" }
  | { type: "CLEAR_RECENT_MOVES" }
  | { type: "CLEAR_RECENT_RDC_LINKS" };

function statsFromSnapshot(data: SessionSnapshot | SessionStartData): Stats {
  return { ...(data.stats ?? INITIAL_STATS) };
}

function applyPhaseChange(
  state: GameState,
  newPhase: string,
): Pick<GameState, "phase" | "phaseToast"> {
  if (newPhase === state.phase) {
    return { phase: state.phase, phaseToast: state.phaseToast };
  }
  const toast = getPhaseTransitionMessage(state.phase, newPhase);
  return {
    phase: newPhase,
    phaseToast: toast ?? state.phaseToast ?? null,
  };
}

function withWorldDelta(
  state: GameState,
  delta: TurnDelta,
  nextSinceTick: number,
): GameState {
  const patch = applyWorldDelta(state, delta);
  return {
    ...state,
    placeId: patch.placeId ?? state.placeId,
    worldTick: Math.max(state.worldTick, patch.worldTick),
    deltaSinceTick: nextSinceTick,
    roomF2f: patch.roomF2f,
    agentLocations: patch.agentLocations,
    agentInbox: patch.agentInbox,
    agentMood: patch.agentMood,
    worldEvents: patch.worldEvents,
    pendingWorldEvent: patch.pendingWorldEvent,
    processedWorldEventIds: patch.processedWorldEventIds,
    recentMoveKeys: patch.recentMoveKeys.length
      ? patch.recentMoveKeys
      : state.recentMoveKeys,
    recentRdcLinks: patch.recentRdcLinks.length
      ? [...state.recentRdcLinks, ...patch.recentRdcLinks].filter(
          (link, index, all) => all.findIndex((item) => item.key === link.key) === index,
        )
      : state.recentRdcLinks,
  };
}

function resetWorldState(): Pick<
  GameState,
  | "roomF2f"
  | "agentLocations"
  | "agentInbox"
  | "agentMood"
  | "worldEvents"
  | "pendingWorldEvent"
  | "processedWorldEventIds"
  | "activeAgentModal"
  | "recentMoveKeys"
  | "recentRdcLinks"
  | "worldTick"
  | "deltaSinceTick"
  | "worldSyncReady"
  | "nameMap"
> {
  return {
    worldTick: 0,
    deltaSinceTick: 0,
    worldSyncReady: false,
    nameMap: {},
    roomF2f: emptyRoomF2f(),
    agentLocations: {},
    agentInbox: {},
    agentMood: {},
    worldEvents: [],
    pendingWorldEvent: null,
    processedWorldEventIds: [],
    activeAgentModal: null,
    recentMoveKeys: [],
    recentRdcLinks: [],
  };
}

export function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case "ENTER_BOOT":
      // 大厅选/建并激活某故事后，进入开局健康检查流程。
      return { ...state, view: "boot", healthChecking: true, healthError: undefined };
    case "HEALTH_CHECK_START":
      return { ...state, healthChecking: true, healthError: undefined };
    case "HEALTH_CHECK_DONE":
      return {
        ...state,
        healthChecking: false,
        runnerReady: action.ready,
        healthError: action.error,
        runnerModalOpen: action.ready ? false : true,
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
        worldLoopState: "running",
        worldLoopPausedAtTick: undefined,
        loading: false,
        ...resetWorldState(),
        phaseToast: null,
        endingId: undefined,
        lastError: undefined,
      };
    case "APPLY_SESSION": {
      if (!action.data.initialized) {
        return { ...state, sessionInitialized: false, view: "boot" };
      }
      const newPhase =
        action.data.phase ?? action.data.current_phase ?? state.phase;
      return {
        ...state,
        view:
          state.view === "game_over" || state.view === "ending"
            ? state.view
            : "playing",
        sessionInitialized: true,
        stats: statsFromSnapshot(action.data),
        ...applyPhaseChange(state, newPhase),
        playerTurn: action.data.player_turn ?? state.playerTurn,
        placeId: action.data.place_id ?? state.placeId,
      };
    }
    case "SET_LOADING":
      return { ...state, loading: action.loading };
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
        roomF2f: pushPlayerBubbleToRoom(
          state.roomF2f,
          state.placeId,
          action.message,
        ),
      };
    case "APPEND_TURN_DELTA":
      return withWorldDelta(state, action.delta, action.delta.through_tick);
    case "APPLY_WORLD_DELTA":
      return withWorldDelta(state, action.delta, action.nextSinceTick);
    case "SET_DELTA_SINCE":
      return { ...state, deltaSinceTick: action.nextSinceTick };
    case "WORLD_SYNC_READY":
      return {
        ...state,
        worldSyncReady: true,
        deltaSinceTick: action.deltaSinceTick,
        worldTick: Math.max(state.worldTick, action.deltaSinceTick),
      };
    case "APPEND_ACTION_RESULT": {
      const phaseUpdate = applyPhaseChange(state, action.data.current_phase);
      return {
        ...withWorldDelta(state, action.data, action.data.through_tick),
        stats: { ...action.data.stats_update },
        ...phaseUpdate,
      };
    }
    case "SET_GAME_OVER":
      return {
        ...withWorldDelta(
          state,
          {
            through_tick: state.worldTick,
            public_messages: action.data.public_messages,
            observer_messages: [],
            group_messages: [],
            player_place_id: state.placeId,
          },
          state.deltaSinceTick,
        ),
        view: "game_over",
        loading: false,
        stats: { ...action.data.stats_update },
        ...applyPhaseChange(state, action.data.current_phase),
      };
    case "SET_ENDING":
      return {
        ...state,
        view: "ending",
        loading: false,
        stats: { ...action.data.stats_update },
        ...applyPhaseChange(state, action.data.current_phase),
        endingId: action.data.ending_id,
      };
    case "SET_ERROR":
      return { ...state, lastError: action.message, loading: false };
    case "SET_RUNNER_MODAL":
      return { ...state, runnerModalOpen: action.open };
    case "DISMISS_PHASE_TOAST":
      return { ...state, phaseToast: null };
    case "SET_WORLD_SNAPSHOT": {
      const snap = applyWorldSnapshot(action.snapshot);
      const snapshotDelta = action.snapshot;
      const deltaPatch = applyWorldDelta(
        {
          placeId: snap.placeId,
          worldTick: state.worldTick,
          roomF2f: state.roomF2f,
          agentLocations: snap.agentLocations,
          agentInbox: state.agentInbox,
          agentMood: state.agentMood,
          worldEvents: state.worldEvents,
          pendingWorldEvent: state.pendingWorldEvent,
          processedWorldEventIds: state.processedWorldEventIds,
        },
        {
          through_tick: snapshotDelta.through_tick,
          player_place_id: snapshotDelta.player_place_id,
          room_f2f: snapshotDelta.room_f2f,
          agent_messages: snapshotDelta.agent_messages,
          location_changes: snapshotDelta.location_changes,
          social_events: snapshotDelta.social_events,
          state_changes: snapshotDelta.state_changes,
          world_events: snapshotDelta.world_events,
          agent_locations: snapshotDelta.agent_locations,
          public_messages: snapshotDelta.public_messages ?? [],
          observer_messages: snapshotDelta.observer_messages ?? [],
          group_messages: snapshotDelta.group_messages ?? [],
        },
      );
      return {
        ...state,
        placeId: deltaPatch.placeId ?? snap.placeId,
        worldTick: Math.max(state.worldTick, deltaPatch.worldTick),
        roomF2f: deltaPatch.roomF2f,
        agentLocations: deltaPatch.agentLocations,
        agentInbox: deltaPatch.agentInbox,
        worldEvents: deltaPatch.worldEvents,
        pendingWorldEvent: deltaPatch.pendingWorldEvent ?? state.pendingWorldEvent,
        processedWorldEventIds: deltaPatch.processedWorldEventIds,
        recentRdcLinks: extractRdcLinks(
          snapshotDelta.agent_messages,
          snapshotDelta.observer_messages ?? [],
        ),
        nameMap: snap.nameMap,
      };
    }
    case "SET_WORLD_LOOP_STATUS":
      return {
        ...state,
        worldLoopState: action.loopState,
        worldLoopPausedAtTick:
          action.loopState === "paused" ? action.pausedAtTick : undefined,
      };
    case "OPEN_AGENT_MODAL":
      return { ...state, activeAgentModal: action.agentId };
    case "CLOSE_AGENT_MODAL":
      return { ...state, activeAgentModal: null };
    case "DISMISS_WORLD_EVENT": {
      const dismissedId = state.pendingWorldEvent?.id;
      const remaining = state.worldEvents.filter(
        (event) => event.id !== dismissedId,
      );
      return {
        ...state,
        worldEvents: remaining,
        pendingWorldEvent: remaining[0] ?? null,
      };
    }
    case "CLEAR_RECENT_MOVES":
      return { ...state, recentMoveKeys: [] };
    case "CLEAR_RECENT_RDC_LINKS":
      return { ...state, recentRdcLinks: [] };
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

export { MAX_TURNS };
