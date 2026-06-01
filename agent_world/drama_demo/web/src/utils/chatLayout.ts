import type { GameMessage } from "../api/types";
import { PLAYER_AGENT_ID } from "../constants/agents";
import { isPlayerMessage } from "./messages";

/** True when message was sent by the chat viewer (player or inbox owner agent). */
export function isChatSelfMessage(
  message: GameMessage,
  viewerId: string,
  nameMap?: Record<string, string>,
): boolean {
  if (message.is_system) {
    return false;
  }
  if (viewerId === PLAYER_AGENT_ID) {
    return isPlayerMessage(message);
  }
  if (message.sender_id != null && message.sender_id >= 0) {
    return String(message.sender_id) === String(viewerId);
  }
  const viewerName = nameMap?.[viewerId];
  if (viewerName) {
    return message.sender === viewerName;
  }
  return false;
}
