// 协议类型（按后端 snapshot.py / ws_hub.py / player_agent.py 1:1 推导）。

export interface GiftItem {
  id: string;
  label: string;
}
export interface NpcInteractions {
  gifts?: GiftItem[];
  helps?: GiftItem[];
  companions?: GiftItem[];
}

export interface HelloAck {
  protocol_version?: number;
  player_agent_id: number;
  tick_interval_ms?: number;
  clock?: { start_time?: string; minutes_per_tick?: number };
  places?: { place_id: string; summary?: string; roster_visible?: boolean }[];
  agents: Record<string, string>; // id -> 显示名
  groups?: { group_id: number; name: string; members: number[] }[];
  // 送心意/搭把手目录（服务端定义，按 npc_id 枚举）——焐心小镇支柱3
  interactions?: Record<string, NpcInteractions>;
}

export interface AgentState {
  name?: string;
  location?: string;
  is_player?: boolean;
  current_state?: string;
  bubble?: string | null;
  affinity_to_player?: number | null;
  activity?: string; // B1 活动动画语义：work/sit/lie/cheer/idle（后端按 current_state 派生）
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

export interface DailyDigest {
  day: number;
  ended_phase: string;
  warmth: number;
  changes: { name: string; delta: number; level: string }[];
  visitors: string[];
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
  daily_digest?: DailyDigest | null;
  bonds?: Record<string, Record<string, string>>; // B4 羁绊：{src:{dst:'好友'|'心结'}}（好感派生）
}

export interface SnapshotFrame {
  type: "snapshot";
  seq: number;
  t: number;
  data: SnapshotData;
}

// 上行命令：5 个引擎白名单 + 2 个交互薄层命令（后端翻译成 speak_to_local）
export type CommandAction =
  | "speak_to_local"
  | "send_message"
  | "send_to_group"
  | "request_move"
  | "do_nothing"
  | "give_gift"
  | "lend_a_hand"
  | "spend_time";
