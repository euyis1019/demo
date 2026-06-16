import { create } from "zustand";
import type { AgentState, Contact, HelloAck, PlayerView, SnapshotData } from "../net/protocol";

// 单一数据中枢：WS 收到帧后只 setState 顶层切片；组件按需 selector 订阅。
interface WorldState {
  connected: boolean;
  playerId: number;
  hello: HelloAck | null;
  tickIntervalMs: number;
  t: number;
  agents: Record<string, AgentState>;
  places: Record<string, { occupants?: number[] }>;
  playerView: PlayerView;
  contacts: Contact[];
  worldTime: string;
  worldEvent: string | null;
  moves: Record<string, string>;

  setConnected: (c: boolean) => void;
  applyHello: (h: HelloAck) => void;
  applySnapshot: (t: number, d: SnapshotData) => void;
}

export const useWorld = create<WorldState>((set) => ({
  connected: false,
  playerId: 0,
  hello: null,
  tickIntervalMs: 2500,
  t: 0,
  agents: {},
  places: {},
  playerView: {},
  contacts: [],
  worldTime: "",
  worldEvent: null,
  moves: {},

  setConnected: (c) => set({ connected: c }),
  applyHello: (h) =>
    set({
      hello: h,
      playerId: h.player_agent_id ?? 0,
      tickIntervalMs: h.tick_interval_ms ?? 2500,
    }),
  applySnapshot: (t, d) =>
    set({
      t,
      agents: d.agents ?? {},
      places: d.places ?? {},
      playerView: d.player_view ?? {},
      contacts: d.contacts ?? [],
      worldTime: d.world_time ?? "",
      worldEvent: d.world_event ?? null,
      moves: d.moves ?? {},
    }),
}));
