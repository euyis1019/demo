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
  /** 按台词内容标注的情绪标签，剧情立绘据此随「说的话」切表情。 */
  emotion?: string;
  attempted_at?: number;
  recipient?: string;
  group_id?: number;
  place_id?: string;
  sender_id?: number;
  recipient_id?: number;
  delivered?: 0 | 1;
  is_system?: boolean;
  prompt_trace_id?: string;
  ref_key?: string;
  /** Client-only: optimistic bubble before world-delta confirms player F2F. */
  _optimistic?: boolean;
}

export interface LocationChange {
  agent_id: number;
  from_place: string | null;
  to_place: string;
  at_tick: number;
  source: string;
  prompt_trace_id?: string;
  ref_key?: string;
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
  /** 离散情绪标签（neutral/happy/angry/sad/anxious/confident），前端据此切立绘。 */
  emotion?: string;
  prompt_trace_id?: string;
  ref_key?: string;
}

export interface PromptTraceLink {
  link_kind: string;
  ref_key: string;
  agent_id: number;
  at_tick: number;
}

export interface PromptTraceData {
  trace_id: string;
  agent_id: number;
  at_tick: number;
  phase?: string | null;
  player_turn?: number | null;
  model?: string;
  temperature?: number | null;
  max_tokens?: number | null;
  system_prompt: string;
  user_prompt: string;
  tool_calls: Array<{ name: string; args: Record<string, unknown> }>;
  assistant_content?: string | null;
  created_at?: string;
  links: PromptTraceLink[];
}

export interface AgentLocation {
  place_id: string;
  arrived_at: number;
}

export interface AgentMessageBucket {
  rdc: GameMessage[];
  grp: GameMessage[];
}

export interface WorldSnapshot extends Partial<TurnDelta> {
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
  phase3_start_tick?: number | null;
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
  stats_update: Stats;
  current_phase: string;
  start_tick: number;
  ipc_end_tick?: number;
}

export interface PlayerTurnGameOver {
  status: "game_over";
  /** 任意故事的结局 id（不再写死）。 */
  ending_id: string;
  /** 该结局的一句话描述（后端按故事下发，数据驱动）。 */
  ending_summary?: string;
  /** 结局好坏：good | neutral | bad。 */
  ending_kind?: string;
  public_messages?: GameMessage[];
  stats_update: Stats;
  current_phase: string;
}

export interface PlayerTurnCompleted {
  status: "completed";
  /** 任意故事的结局 id（不再写死）。 */
  ending_id: string;
  ending_summary?: string;
  ending_kind?: string;
  intent?: string;
  stats_update: Stats;
  current_phase: string;
}

export interface PlayerTurnAccepted {
  accepted: true;
  stats_update: Stats;
  current_phase: string;
  player_turn: number;
}

export type PlayerTurnData =
  | PlayerTurnAccepted
  | PlayerTurnProcessing
  | PlayerTurnGameOver
  | PlayerTurnCompleted;

export interface WorldDeltaData extends TurnDelta {
  current_tick: number;
  loop_state?: string;
  stats_update: Stats;
  current_phase: string;
  /** 故事张力 0–100（drama-manager 导演每拍更新）。 */
  tension?: number;
  player_turn: number;
  /** F14 RoutingWatcher finale: bad_reject (status "game_over") OR the
   *  offer-driven Phase-4 early end (status "completed" → EndingScreen). */
  game_over?: PlayerTurnGameOver | PlayerTurnCompleted;
}

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
