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
  sender_id?: number;
  recipient_id?: number;
  delivered?: 0 | 1;
  is_system?: boolean;
}

export interface LocationChange {
  agent_id: number;
  from_place: string | null;
  to_place: string;
  at_tick: number;
  source: string;
}

export interface WorldEvent {
  id: string;
  at_tick: number;
  kind: "broadcast" | "phase_route" | "place_mutation" | "bad_end" | "system";
  title?: string;
  content: string;
  place_id?: string;
}

export interface SocialEvent {
  at_tick: number;
  kind:
    | "relation_add"
    | "relation_remove"
    | "group_join"
    | "group_leave"
    | "group_kick";
  agent_id: number;
  peer_id?: number;
  group_id?: number;
  relation_type?: string;
}

export interface StateChange {
  agent_id: number;
  content: string;
  at_tick: number;
}

export interface AgentLocation {
  place_id: string;
  arrived_at: number;
}

export interface AgentMessageBucket {
  rdc: GameMessage[];
  grp: GameMessage[];
}

export interface WorldSnapshot {
  through_tick: number;
  player_place_id: string;
  agent_locations: Record<string, AgentLocation>;
  place_attrs: Record<string, Record<string, unknown>>;
  relations: Array<Record<string, unknown>>;
  group_members: Record<string, number[]>;
  name_map: Record<string, string>;
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
  loop_state?: string;
  loop_running?: boolean;
  paused_at_tick?: number;
  paused_at_iso?: string;
  tick_interval_sec?: number;
  [key: string]: unknown;
}

export type WorldLoopState = "running" | "paused" | "stopped" | "disabled" | "unknown";

export interface WorldLoopStatusData {
  loop_state: WorldLoopState | string;
  loop_running: boolean;
  current_tick: number;
  world_t: number;
  tick_interval_sec: number;
  paused_at_tick?: number | null;
  paused_at_iso?: string | null;
  queue_depth?: number;
  last_activity_t?: number;
  already_paused?: boolean;
  already_running?: boolean;
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
  through_tick: number;
  player_place_id?: string;
  room_f2f?: Partial<Record<string, GameMessage[]>>;
  agent_messages?: Record<string, AgentMessageBucket>;
  location_changes?: LocationChange[];
  social_events?: SocialEvent[];
  state_changes?: StateChange[];
  world_events?: WorldEvent[];
  agent_locations?: Record<string, AgentLocation>;
  /** @deprecated F11 legacy — use room_f2f */
  public_messages: GameMessage[];
  /** @deprecated F11 legacy — use agent_messages */
  observer_messages: GameMessage[];
  /** @deprecated F11 legacy — use agent_messages */
  group_messages: GameMessage[];
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

export interface ActionResultCompleted extends TurnDelta {
  status: "completed";
  task_id: string;
  end_tick: number;
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

export interface ActionResultError {
  status: "error";
  task_id: string;
  inject_status?: string;
  error?: string;
}

export type ActionResultData =
  | ActionResultProcessing
  | ActionResultCompleted
  | ActionResultGameOver
  | ActionResultError;

export interface PlayerTurnRequest {
  player_text: string;
  tick_count?: number;
  place_id?: string;
  phase?: string;
  player_turn?: number;
}
