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

/** PLAN2 F4-3 — sort by attempted_at ascending. */
export function sortMessages(messages: GameMessage[]): GameMessage[] {
  return [...messages].sort(
    (a, b) => (a.attempted_at ?? 0) - (b.attempted_at ?? 0),
  );
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
