import type {
  GameMessage,
  LocationChange,
  SocialEvent,
  StateChange,
} from "../api/types";
import { mergeMessages, messageKey } from "../utils/messages";

/** Per-agent inbox (the "agent phone" domain): RDC / GRP threads + OS / move logs. */
export interface AgentInbox {
  rdc: GameMessage[];
  grp: GameMessage[];
  osLog: StateChange[];
  locationLog: LocationChange[];
  archivedThreadKeys: string[];
}

export function emptyAgentInbox(): AgentInbox {
  return { rdc: [], grp: [], osLog: [], locationLog: [], archivedThreadKeys: [] };
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

export function threadKeyRdc(message: GameMessage, ownerAgentId: string): string {
  return `rdc:${rdcPeerId(message, ownerAgentId)}`;
}

export function threadKeyGrp(message: GameMessage): string {
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

export function applySocialEvents(
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

export function mergeAgentMessages(
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

export function mergeStateChanges(
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

export function mergeLocationChanges(
  agentInbox: Record<string, AgentInbox>,
  changes: LocationChange[] | undefined,
): Record<string, AgentInbox> {
  if (!changes?.length) {
    return agentInbox;
  }
  const next = { ...agentInbox };
  for (const change of changes) {
    const key = String(change.agent_id);
    const inbox = { ...(next[key] ?? emptyAgentInbox()) };
    const exists = inbox.locationLog.some(
      (row) =>
        row.at_tick === change.at_tick &&
        row.from_place === change.from_place &&
        row.to_place === change.to_place,
    );
    if (!exists) {
      inbox.locationLog = [...inbox.locationLog, change].sort(
        (a, b) => a.at_tick - b.at_tick,
      );
    }
    next[key] = inbox;
  }
  return next;
}

export function mergeLegacyObserverIntoInbox(
  agentInbox: Record<string, AgentInbox>,
  observerMessages: GameMessage[] | undefined,
  groupMessages: GameMessage[] | undefined,
): Record<string, AgentInbox> {
  const next = agentInbox;
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

export function extractRdcLinks(
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
