// 协议类型（按后端 snapshot.py / ws_hub.py / player_agent.py 1:1 推导）。

export interface HelloAck {
  protocol_version?: number;
  player_agent_id: number;
  tick_interval_ms?: number;
  clock?: { start_time?: string; minutes_per_tick?: number };
  places?: { place_id: string; summary?: string; roster_visible?: boolean }[];
  agents: Record<string, string>; // id -> 显示名
  groups?: { group_id: number; name: string; members: number[] }[];
}

export interface AgentState {
  name?: string;
  location?: string;
  is_player?: boolean;
  current_state?: string;
  bubble?: string | null;
  affinity_to_player?: number | null;
}

export interface MsgRow {
  message_id?: number;
  sender_id?: number;
  recipient_id?: number;
  group_id?: number;
  group_name?: string;
  content?: string;
  channel_type?: string;
  attempted_at?: number;
  reason?: string;
}

export interface PlayerView {
  incoming?: MsgRow[];
  f2f?: MsgRow[];
  overheard?: MsgRow[];
  failed?: MsgRow[];
  group?: MsgRow[];
  group_events?: any[];
}

export interface Contact {
  agent_id: number;
  name?: string;
  can_reach_now?: boolean;
  reason?: string;
  relation_types?: string[];
}

export interface SnapshotData {
  agents: Record<string, AgentState>;
  places: Record<string, { occupants?: number[] }>;
  player_view?: PlayerView;
  world_time?: string;
  world_event?: string | null;
  recent_arrivals?: number[];
  recent_departures?: number[];
  moves?: Record<string, string>;
  contacts?: Contact[];
  affinity?: any;
  failures?: any[];
}

export interface SnapshotFrame {
  type: "snapshot";
  seq: number;
  t: number;
  data: SnapshotData;
}

// 上行命令（白名单 5 个）
export type CommandAction =
  | "speak_to_local"
  | "send_message"
  | "send_to_group"
  | "request_move"
  | "do_nothing";
