import type { GameMessage } from "../api/types";
import { PLAYER_SENDER } from "../constants/gameLoop";

export const TERMINAL_SENDER = "彭博终端";

export function isPlayerSender(sender: string): boolean {
  return sender === PLAYER_SENDER || sender === "Player";
}

/** Player-authored F2F (UI bubble or backend virtual agent 0). */
export function isPlayerMessage(message: GameMessage): boolean {
  if (message.is_system) {
    return false;
  }
  return isPlayerSender(message.sender) || message.sender_id === 0;
}

export function messageKey(message: GameMessage): string {
  if (message.type === "F2F" && isPlayerMessage(message)) {
    const place = message.place_id ?? "";
    return ["F2F", "player", place, message.content.trim()].join("|");
  }
  return [
    message.type,
    message.sender,
    message.recipient ?? "",
    message.group_id ?? "",
    message.attempted_at ?? "",
    message.content,
  ].join("|");
}

export function messageReactKey(message: GameMessage, index: number): string {
  return `${messageKey(message)}-${index}`;
}

export function maxAttemptedAt(messages: GameMessage[]): number {
  return messages.reduce(
    (max, message) => Math.max(max, message.attempted_at ?? 0),
    0,
  );
}

/** Place player bubble after existing F2F but before the next NPC batch (world ticks are ints). */
export function stampPlayerBubble(
  existing: GameMessage[],
  message: GameMessage,
): GameMessage {
  return {
    ...message,
    attempted_at: maxAttemptedAt(existing) + 0.5,
    _optimistic: true,
  };
}

function replaceOptimisticPlayerBubble(
  merged: GameMessage[],
  incoming: GameMessage,
): boolean {
  if (incoming.type !== "F2F" || !isPlayerMessage(incoming)) {
    return false;
  }
  const content = incoming.content.trim();
  const optIdx = merged.findIndex(
    (row) => row._optimistic && row.content.trim() === content,
  );
  if (optIdx < 0) {
    return false;
  }
  const prev = merged[optIdx];
  merged[optIdx] = {
    ...incoming,
    sender: incoming.sender || prev.sender,
    attempted_at: prev.attempted_at ?? incoming.attempted_at,
    ref_key: incoming.ref_key ?? prev.ref_key,
    prompt_trace_id: incoming.prompt_trace_id ?? prev.prompt_trace_id,
    _optimistic: undefined,
  };
  return true;
}

function mergeDuplicatePlayerF2f(
  merged: GameMessage[],
  incoming: GameMessage,
): boolean {
  if (incoming.type !== "F2F" || !isPlayerMessage(incoming)) {
    return false;
  }
  const content = incoming.content.trim();
  const place = incoming.place_id ?? "";
  const dupIdx = merged.findIndex(
    (row) =>
      row.type === "F2F" &&
      isPlayerMessage(row) &&
      row.content.trim() === content &&
      (row.place_id ?? "") === place,
  );
  if (dupIdx < 0) {
    return false;
  }
  const prev = merged[dupIdx];
  merged[dupIdx] = {
    ...incoming,
    sender: incoming.sender || prev.sender,
    attempted_at: prev.attempted_at ?? incoming.attempted_at,
    ref_key: incoming.ref_key ?? prev.ref_key,
    prompt_trace_id: incoming.prompt_trace_id ?? prev.prompt_trace_id,
    _optimistic: undefined,
  };
  return true;
}

/** PLAN2 F4-3 — sort by attempted_at; tie-break player before NPC at same tick. */
export function sortMessages(messages: GameMessage[]): GameMessage[] {
  return [...messages].sort((a, b) => {
    const atDiff = (a.attempted_at ?? 0) - (b.attempted_at ?? 0);
    if (atDiff !== 0) {
      return atDiff;
    }
    const aPlayer = isPlayerSender(a.sender) ? 0 : 1;
    const bPlayer = isPlayerSender(b.sender) ? 0 : 1;
    return aPlayer - bPlayer;
  });
}

export function mergeMessages(
  existing: GameMessage[],
  incoming: GameMessage[] | undefined,
): GameMessage[] {
  if (!incoming?.length) {
    return sortMessages(existing);
  }
  const indexByKey = new Map(existing.map((message, index) => [messageKey(message), index]));
  const merged = [...existing];
  for (const message of incoming) {
    if (replaceOptimisticPlayerBubble(merged, message)) {
      continue;
    }
    if (mergeDuplicatePlayerF2f(merged, message)) {
      continue;
    }
    const key = messageKey(message);
    const existingIndex = indexByKey.get(key);
    if (existingIndex != null) {
      const prev = merged[existingIndex];
      if (
        (message.ref_key && !prev.ref_key) ||
        (message.prompt_trace_id && !prev.prompt_trace_id)
      ) {
        merged[existingIndex] = {
          ...prev,
          ref_key: prev.ref_key ?? message.ref_key,
          prompt_trace_id: prev.prompt_trace_id ?? message.prompt_trace_id,
        };
      }
      continue;
    }
    indexByKey.set(key, merged.length);
    merged.push(message);
  }
  return sortMessages(merged);
}
