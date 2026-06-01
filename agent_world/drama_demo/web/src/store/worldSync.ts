import type {
  AgentLocation,
  GameMessage,
  TurnDelta,
  WorldEvent,
  WorldSnapshot,
} from "../api/types";
import { PLAYER_AGENT_ID, VIRTUAL_PLAYER_AGENT_ID } from "../constants/agents";
import { PLAYER_SENDER } from "../constants/gameLoop";
import type { PlaceId } from "../utils/places";
import { mergeMessages, stampPlayerBubble } from "../utils/messages";
import {
  applySocialEvents,
  emptyAgentInbox,
  extractRdcLinks,
  mergeAgentMessages,
  mergeLegacyObserverIntoInbox,
  mergeLocationChanges,
  mergeStateChanges,
  rdcPeerId,
  threadKeyGrp,
  threadKeyRdc,
  type AgentInbox,
  type RdcLink,
} from "./agentInbox";

// Re-export the agent-inbox public API so existing `from ".../store/worldSync"`
// imports keep resolving (the inbox/messages domain now lives in agentInbox.ts).
export {
  applySocialEvents,
  emptyAgentInbox,
  extractRdcLinks,
  rdcPeerId,
  threadKeyGrp,
  threadKeyRdc,
  type AgentInbox,
  type RdcLink,
};

export function normalizeAgentLocations(
  raw: Record<string, AgentLocation> | undefined,
): Record<string, { placeId: string; arrivedAt: number }> {
  if (!raw) {
    return {};
  }
  const out: Record<string, { placeId: string; arrivedAt: number }> = {};
  for (const [agentId, info] of Object.entries(raw)) {
    const id = String(agentId);
    // Backend F17 agent 0 duplicates UI player pseudo-id; skip to avoid twin circles.
    if (id === VIRTUAL_PLAYER_AGENT_ID) {
      continue;
    }
    out[id] = {
      placeId: String(info.place_id),
      arrivedAt: Number(info.arrived_at ?? 0),
    };
  }
  return out;
}

function mergeRoomF2f(
  roomF2f: Record<PlaceId, GameMessage[]>,
  incoming: Partial<Record<string, GameMessage[]>> | undefined,
  legacyPublic: GameMessage[] | undefined,
  playerPlaceId: string,
): Record<PlaceId, GameMessage[]> {
  const next: Record<string, GameMessage[]> = { ...roomF2f };
  if (incoming) {
    // 按后端实际下发的地点 key 合并（支持任意故事的地点 id，含中文）——不再只认写死的 4 个旧 HBM
    // 地点，否则数据驱动故事（如沧澜剑「后庭院」）的对话会被整段丢弃、剧情模式什么都显示不出来。
    for (const [placeId, messages] of Object.entries(incoming)) {
      if (messages?.length) {
        next[placeId] = mergeMessages(next[placeId] ?? [], messages);
      }
    }
  }
  if (legacyPublic?.length) {
    const place = playerPlaceId;  // 直接用玩家当前地点，不再回退到 nvidia_reception
    // F12: public_messages mirrors room_f2f[player_place] — skip when already in this delta.
    const alreadyInRoomF2f = Boolean(incoming?.[place]?.length);
    if (!alreadyInRoomF2f) {
      next[place] = mergeMessages(next[place] ?? [], legacyPublic);
    }
  }
  return next as Record<PlaceId, GameMessage[]>;
}

export interface WorldDeltaPatch {
  placeId?: string;
  worldTick: number;
  roomF2f: Record<PlaceId, GameMessage[]>;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  agentInbox: Record<string, AgentInbox>;
  /** 每个 agent 最新情绪标签（来自 state_changes.emotion），前端据此切立绘。 */
  agentMood: Record<string, string>;
  worldEvents: WorldEvent[];
  pendingWorldEvent: WorldEvent | null;
  processedWorldEventIds: string[];
  recentMoveKeys: string[];
  recentRdcLinks: RdcLink[];
}

function mergeWorldEvents(
  currentEvents: WorldEvent[],
  pending: WorldEvent | null,
  processedIds: string[],
  incoming: WorldEvent[] | undefined,
): {
  worldEvents: WorldEvent[];
  pendingWorldEvent: WorldEvent | null;
  processedWorldEventIds: string[];
} {
  const processed = new Set(processedIds);
  const worldEvents = [...currentEvents];
  let pendingWorldEvent = pending;

  for (const event of incoming ?? []) {
    const eventId = String(event.id ?? "");
    if (!eventId || processed.has(eventId)) {
      continue;
    }
    if (worldEvents.some((existing) => existing.id === eventId)) {
      continue;
    }
    worldEvents.push(event);
    processed.add(eventId);
    if (!pendingWorldEvent) {
      pendingWorldEvent = event;
    }
  }

  return {
    worldEvents,
    pendingWorldEvent,
    processedWorldEventIds: [...processed],
  };
}

export function applyWorldDelta(
  current: {
    placeId: string;
    worldTick: number;
    roomF2f: Record<PlaceId, GameMessage[]>;
    agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
    agentInbox: Record<string, AgentInbox>;
    agentMood: Record<string, string>;
    worldEvents: WorldEvent[];
    pendingWorldEvent: WorldEvent | null;
    processedWorldEventIds: string[];
  },
  delta: TurnDelta,
): WorldDeltaPatch {
  const playerPlace = delta.player_place_id ?? current.placeId;
  const roomF2f = mergeRoomF2f(
    current.roomF2f,
    delta.room_f2f,
    delta.public_messages,
    playerPlace,
  );
  let agentInbox = mergeLegacyObserverIntoInbox(
    mergeAgentMessages(current.agentInbox, delta.agent_messages),
    delta.observer_messages,
    delta.group_messages,
  );
  agentInbox = applySocialEvents(agentInbox, delta.social_events);
  agentInbox = mergeStateChanges(agentInbox, delta.state_changes);
  agentInbox = mergeLocationChanges(agentInbox, delta.location_changes);

  const agentLocations = delta.agent_locations
    ? normalizeAgentLocations(delta.agent_locations)
    : { ...current.agentLocations };

  agentLocations[PLAYER_AGENT_ID] = {
    placeId: playerPlace,
    arrivedAt: delta.through_tick,
  };

  const eventPatch = mergeWorldEvents(
    current.worldEvents,
    current.pendingWorldEvent,
    current.processedWorldEventIds,
    delta.world_events,
  );

  const recentMoveKeys: string[] = [];
  for (const change of delta.location_changes ?? []) {
    if (change.from_place !== change.to_place) {
      recentMoveKeys.push(`${change.agent_id}:${change.at_tick}`);
    }
  }

  const recentRdcLinks = extractRdcLinks(delta.agent_messages, delta.observer_messages);

  // 情绪：取每个 agent state_changes 里最新一条的 emotion，并入既有 mood。
  const agentMood: Record<string, string> = { ...current.agentMood };
  for (const sc of delta.state_changes ?? []) {
    if (sc.emotion) {
      agentMood[String(sc.agent_id)] = sc.emotion;
    }
  }

  return {
    placeId: playerPlace,
    worldTick: delta.through_tick,
    roomF2f,
    agentLocations,
    agentInbox,
    agentMood,
    worldEvents: eventPatch.worldEvents,
    pendingWorldEvent: eventPatch.pendingWorldEvent,
    processedWorldEventIds: eventPatch.processedWorldEventIds,
    recentMoveKeys,
    recentRdcLinks,
  };
}

export function applyWorldSnapshot(snapshot: WorldSnapshot): {
  placeId: string;
  worldTick: number;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  nameMap: Record<string, string>;
} {
  const agentLocations = normalizeAgentLocations(snapshot.agent_locations);
  agentLocations[PLAYER_AGENT_ID] = {
    placeId: snapshot.player_place_id,
    arrivedAt: snapshot.through_tick,
  };
  return {
    placeId: snapshot.player_place_id,
    worldTick: snapshot.through_tick,
    agentLocations,
    nameMap: snapshot.name_map ?? {},
  };
}

export function pushPlayerBubbleToRoom(
  roomF2f: Record<PlaceId, GameMessage[]>,
  placeId: string,
  message: GameMessage,
): Record<PlaceId, GameMessage[]> {
  // 直接用玩家当前地点（任意故事地点 id，含中文）——不再回退到 nvidia_reception，
  // 否则玩家台词被推到错误房间、剧情字幕上看不到自己说的话。
  const place = placeId;
  const existing = (roomF2f as Record<string, GameMessage[]>)[place] ?? [];
  return {
    ...roomF2f,
    [place]: mergeMessages(existing, [
      stampPlayerBubble(existing, {
        ...message,
        sender: PLAYER_SENDER,
        type: "F2F",
        place_id: place,
      }),
    ]),
  } as Record<PlaceId, GameMessage[]>;
}

export function agentsInPlace(
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>,
  placeId: string,
): string[] {
  return Object.entries(agentLocations)
    .filter(([, loc]) => loc.placeId === placeId)
    .map(([id]) => id)
    .sort((a, b) => {
      if (a === PLAYER_AGENT_ID) {
        return 1;
      }
      if (b === PLAYER_AGENT_ID) {
        return -1;
      }
      return Number(a) - Number(b);
    });
}

export function moveKeyForAgent(agentId: string, recentMoveKeys: string[]): boolean {
  return recentMoveKeys.some((key) => key.startsWith(`${agentId}:`));
}
