/** API JSON types — aligned with `routes.py` + PLAN2 appendix A. */

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface Stats {
  vision: number;
  execution: number;
  trust: number;
  burnout: number;
}

export interface GameMessage {
  sender: string;
  content: string;
  type: "F2F" | "RDC" | "GRP";
  attempted_at?: number;
  recipient?: string;
  group_id?: number;
  place_id?: string;
}

export interface HealthData {
  sim_dir: string;
  runner_ready: boolean;
  world_db_readable: boolean;
  ready: boolean;
  env_status?: Record<string, unknown>;
  db_error?: string | null;
}

export interface SessionSnapshot {
  initialized: boolean;
  sim_id?: string;
  runner_ready: boolean;
  task_id?: string;
  start_tick?: number;
  place_id?: string;
  phase?: string;
  current_phase?: string;
  player_turn?: number;
  stats?: Stats;
  stats_update?: Stats;
  phase2_start_tick?: number | null;
  env_status?: Record<string, unknown>;
}

export interface SessionStartData {
  task_id: string;
  start_tick: number;
  place_id: string;
  phase: string;
  player_turn: number;
  stats: Stats;
  env_status?: Record<string, unknown>;
}

export interface EnvStatusData {
  status?: string;
  current_tick?: number;
  timestamp?: string;
  [key: string]: unknown;
}

export interface PlayerTurnProcessing {
  status: "processing";
  task_id: string;
  immediate_msg: string;
  stats_update: Stats;
  current_phase: string;
  start_tick: number;
  ipc_end_tick?: number;
}

export interface PlayerTurnGameOver {
  status: "game_over";
  ending_id: "bad_reject";
  public_messages: GameMessage[];
  stats_update: Stats;
  current_phase: string;
}

export interface PlayerTurnCompleted {
  status: "completed";
  ending_id: "ending_join_nvidia" | "ending_seed_round" | "ending_cold_deal";
  intent?: string;
  immediate_msg?: string;
  stats_update: Stats;
  current_phase: string;
}

export type PlayerTurnData =
  | PlayerTurnProcessing
  | PlayerTurnGameOver
  | PlayerTurnCompleted;

export interface TurnDelta {
  public_messages: GameMessage[];
  observer_messages: GameMessage[];
  group_messages: GameMessage[];
  through_tick: number;
}

export interface ActionResultProcessing {
  status: "processing";
  task_id: string;
  current_tick?: number;
  effective_tick?: number;
  start_tick?: number;
  ipc_end_tick?: number | null;
  inject_status?: string;
  delta?: TurnDelta;
}

export interface ActionResultCompleted {
  status: "completed";
  task_id: string;
  end_tick: number;
  public_messages: GameMessage[];
  observer_messages: GameMessage[];
  group_messages: GameMessage[];
  stats_update: Stats;
  current_phase: string;
}

export interface ActionResultGameOver {
  status: "game_over";
  task_id: string;
  ending_id: "bad_reject";
  public_messages: GameMessage[];
  stats_update: Stats;
  current_phase: string;
}

export type ActionResultData =
  | ActionResultProcessing
  | ActionResultCompleted
  | ActionResultGameOver;

export interface PlayerTurnRequest {
  player_text: string;
  tick_count?: number;
  place_id?: string;
  phase?: string;
  player_turn?: number;
}
