import type {
  AgentLocation,
  GameMessage,
  SocialEvent,
  StateChange,
  TurnDelta,
  WorldEvent,
  WorldSnapshot,
} from "../api/types";
import { PLAYER_AGENT_ID } from "../constants/agents";
import { PLAYER_SENDER } from "../constants/gameLoop";
import type { PlaceId } from "../utils/places";
import { ROOM_GRID } from "../utils/places";
import { mergeMessages, messageKey, stampPlayerBubble } from "../utils/messages";

export interface AgentInbox {
  rdc: GameMessage[];
  grp: GameMessage[];
  osLog: StateChange[];
  archivedThreadKeys: string[];
}

export function emptyAgentInbox(): AgentInbox {
  return { rdc: [], grp: [], osLog: [], archivedThreadKeys: [] };
}

export function normalizeAgentLocations(
  raw: Record<string, AgentLocation> | undefined,
): Record<string, { placeId: string; arrivedAt: number }> {
  if (!raw) {
    return {};
  }
  const out: Record<string, { placeId: string; arrivedAt: number }> = {};
  for (const [agentId, info] of Object.entries(raw)) {
    out[String(agentId)] = {
      placeId: String(info.place_id),
      arrivedAt: Number(info.arrived_at ?? 0),
    };
  }
  return out;
}

export function rdcPeerId(message: GameMessage, ownerAgentId: string): string {
  const owner = String(ownerAgentId);
  const senderId =
    message.sender_id != null && message.sender_id >= 0
      ? String(message.sender_id)
      : null;
  const recipientId =
    message.recipient_id != null ? String(message.recipient_id) : null;

  if (senderId === owner && recipientId && recipientId !== owner) {
    return recipientId;
  }
  if (recipientId === owner && senderId && senderId !== owner) {
    return senderId;
  }
  if (senderId && senderId !== owner) {
    return senderId;
  }
  if (recipientId && recipientId !== owner) {
    return recipientId;
  }
  return "unknown";
}

function threadKeyRdc(message: GameMessage, ownerAgentId: string): string {
  return `rdc:${rdcPeerId(message, ownerAgentId)}`;
}

function threadKeyGrp(message: GameMessage): string {
  return `grp:${message.group_id ?? "unknown"}`;
}

function systemMessage(content: string, type: "RDC" | "GRP"): GameMessage {
  return {
    sender: "系统",
    content,
    type,
    is_system: true,
    attempted_at: Date.now(),
  };
}

function applySocialEvents(
  agentInbox: Record<string, AgentInbox>,
  events: SocialEvent[] | undefined,
): Record<string, AgentInbox> {
  if (!events?.length) {
    return agentInbox;
  }
  const next = { ...agentInbox };
  for (const event of events) {
    const agentKey = String(event.agent_id);
    const inbox = { ...(next[agentKey] ?? emptyAgentInbox()) };
    if (event.kind === "group_leave" || event.kind === "group_kick") {
      const key = `grp:${event.group_id ?? "unknown"}`;
      if (!inbox.archivedThreadKeys.includes(key)) {
        inbox.archivedThreadKeys = [...inbox.archivedThreadKeys, key];
        inbox.grp = mergeMessages(inbox.grp, [
          systemMessage("您已退出该群聊", "GRP"),
        ]);
      }
    }
    if (event.kind === "relation_remove") {
      const key = `rdc:${event.peer_id ?? "unknown"}`;
      if (!inbox.archivedThreadKeys.includes(key)) {
        inbox.archivedThreadKeys = [...inbox.archivedThreadKeys, key];
        inbox.rdc = mergeMessages(inbox.rdc, [
          systemMessage("与对方关系已断裂", "RDC"),
        ]);
      }
    }
    next[agentKey] = inbox;
  }
  return next;
}

function mergeAgentMessages(
  agentInbox: Record<string, AgentInbox>,
  incoming: Record<string, { rdc?: GameMessage[]; grp?: GameMessage[] }> | undefined,
): Record<string, AgentInbox> {
  if (!incoming) {
    return agentInbox;
  }
  const next = { ...agentInbox };
  for (const [agentId, bucket] of Object.entries(incoming)) {
    const inbox = { ...(next[agentId] ?? emptyAgentInbox()) };
    if (bucket.rdc?.length) {
      inbox.rdc = mergeMessages(inbox.rdc, bucket.rdc);
    }
    if (bucket.grp?.length) {
      inbox.grp = mergeMessages(inbox.grp, bucket.grp);
    }
    next[agentId] = inbox;
  }
  return next;
}

function mergeStateChanges(
  agentInbox: Record<string, AgentInbox>,
  changes: StateChange[] | undefined,
): Record<string, AgentInbox> {
  if (!changes?.length) {
    return agentInbox;
  }
  const next = { ...agentInbox };
  for (const change of changes) {
    const key = String(change.agent_id);
    const inbox = { ...(next[key] ?? emptyAgentInbox()) };
    const exists = inbox.osLog.some(
      (row) =>
        row.at_tick === change.at_tick && row.content === change.content,
    );
    if (!exists) {
      inbox.osLog = [...inbox.osLog, change].sort(
        (a, b) => a.at_tick - b.at_tick,
      );
    }
    next[key] = inbox;
  }
  return next;
}

function mergeRoomF2f(
  roomF2f: Record<PlaceId, GameMessage[]>,
  incoming: Partial<Record<string, GameMessage[]>> | undefined,
  legacyPublic: GameMessage[] | undefined,
  playerPlaceId: string,
): Record<PlaceId, GameMessage[]> {
  const next = { ...roomF2f };
  if (incoming) {
    for (const placeId of ROOM_GRID) {
      const messages = incoming[placeId];
      if (messages?.length) {
        next[placeId] = mergeMessages(next[placeId], messages);
      }
    }
  }
  if (legacyPublic?.length) {
    const place = (playerPlaceId as PlaceId) in next ? (playerPlaceId as PlaceId) : "nvidia_reception";
    next[place] = mergeMessages(next[place], legacyPublic);
  }
  return next;
}

function mergeLegacyObserverIntoInbox(
  agentInbox: Record<string, AgentInbox>,
  observerMessages: GameMessage[] | undefined,
  groupMessages: GameMessage[] | undefined,
): Record<string, AgentInbox> {
  let next = agentInbox;
  if (observerMessages?.length) {
    for (const message of observerMessages) {
      const recipients = [
        message.recipient_id,
        message.sender_id,
      ].filter((id): id is number => typeof id === "number");
      for (const agentId of recipients) {
        const key = String(agentId);
        const inbox = { ...(next[key] ?? emptyAgentInbox()) };
        inbox.rdc = mergeMessages(inbox.rdc, [message]);
        next[key] = inbox;
      }
    }
  }
  if (groupMessages?.length) {
    for (const message of groupMessages) {
      const senderKey =
        message.sender_id !== undefined ? String(message.sender_id) : undefined;
      if (senderKey) {
        const inbox = { ...(next[senderKey] ?? emptyAgentInbox()) };
        inbox.grp = mergeMessages(inbox.grp, [message]);
        next[senderKey] = inbox;
      }
    }
  }
  return next;
}

export interface RdcLink {
  from: string;
  to: string;
  key: string;
}

function extractRdcLinks(
  incoming: Record<string, { rdc?: GameMessage[]; grp?: GameMessage[] }> | undefined,
  observerMessages: GameMessage[] | undefined,
): RdcLink[] {
  const links: RdcLink[] = [];
  const seen = new Set<string>();

  const consider = (message: GameMessage) => {
    if (message.type !== "RDC") {
      return;
    }
    const sender = message.sender_id;
    const recipient = message.recipient_id;
    if (
      sender == null ||
      recipient == null ||
      sender < 0 ||
      recipient < 0 ||
      sender === recipient
    ) {
      return;
    }
    const key = messageKey(message);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    links.push({ from: String(sender), to: String(recipient), key });
  };

  if (incoming) {
    for (const bucket of Object.values(incoming)) {
      for (const message of bucket.rdc ?? []) {
        consider(message);
      }
    }
  }
  for (const message of observerMessages ?? []) {
    consider(message);
  }
  return links;
}

export interface WorldDeltaPatch {
  placeId?: string;
  worldTick: number;
  roomF2f: Record<PlaceId, GameMessage[]>;
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  agentInbox: Record<string, AgentInbox>;
  worldEvents: WorldEvent[];
  pendingWorldEvent: WorldEvent | null;
  recentMoveKeys: string[];
  recentRdcLinks: RdcLink[];
}

export function applyWorldDelta(
  current: {
    placeId: string;
    worldTick: number;
    roomF2f: Record<PlaceId, GameMessage[]>;
    agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
    agentInbox: Record<string, AgentInbox>;
    worldEvents: WorldEvent[];
    pendingWorldEvent: WorldEvent | null;
  },
  delta: TurnDelta,
): WorldDeltaPatch {
  const playerPlace = delta.player_place_id ?? current.placeId;
  let roomF2f = mergeRoomF2f(
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

  const agentLocations = delta.agent_locations
    ? normalizeAgentLocations(delta.agent_locations)
    : { ...current.agentLocations };

  agentLocations[PLAYER_AGENT_ID] = {
    placeId: playerPlace,
    arrivedAt: delta.through_tick,
  };

  const worldEvents = [...current.worldEvents];
  let pendingWorldEvent = current.pendingWorldEvent;
  for (const event of delta.world_events ?? []) {
    if (!worldEvents.some((existing) => existing.id === event.id)) {
      worldEvents.push(event);
      if (!pendingWorldEvent) {
        pendingWorldEvent = event;
      }
    }
  }

  const recentMoveKeys: string[] = [];
  for (const change of delta.location_changes ?? []) {
    if (change.from_place !== change.to_place) {
      recentMoveKeys.push(`${change.agent_id}:${change.at_tick}`);
    }
  }

  const recentRdcLinks = extractRdcLinks(delta.agent_messages, delta.observer_messages);

  return {
    placeId: playerPlace,
    worldTick: delta.through_tick,
    roomF2f,
    agentLocations,
    agentInbox,
    worldEvents,
    pendingWorldEvent,
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
  const place = (ROOM_GRID.includes(placeId as PlaceId)
    ? placeId
    : "nvidia_reception") as PlaceId;
  return {
    ...roomF2f,
    [place]: mergeMessages(roomF2f[place], [
      stampPlayerBubble(roomF2f[place], {
        ...message,
        sender: PLAYER_SENDER,
        type: "F2F",
        place_id: place,
      }),
    ]),
  };
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

export { threadKeyRdc, threadKeyGrp };
