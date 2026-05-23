import type { GameMessage } from "../api/types";
import { PLAYER_SENDER } from "../constants/gameLoop";

export const TERMINAL_SENDER = "彭博终端";

export function isPlayerSender(sender: string): boolean {
  return sender === PLAYER_SENDER || sender === "Player";
}

export function messageKey(message: GameMessage): string {
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
  };
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
  const seen = new Set(existing.map(messageKey));
  const merged = [...existing];
  for (const message of incoming) {
    const key = messageKey(message);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(message);
  }
  return sortMessages(merged);
}
