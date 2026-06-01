import type { GameMessage } from "../../../api/types";
import { PLAYER_AGENT_ID } from "../../../constants/agents";
import { isPlayerSender } from "../../../utils/messages";

/** Map an F2F message to the speaking agent id in the room grid. */
export function resolveSpeakerAgentId(
  message: GameMessage,
  nameMap: Record<string, string>,
): string | null {
  if (message.sender_id != null && Number(message.sender_id) === 0) {
    return PLAYER_AGENT_ID;
  }
  if (isPlayerSender(message.sender)) {
    return PLAYER_AGENT_ID;
  }
  if (message.sender_id != null) {
    return String(message.sender_id);
  }
  for (const [id, name] of Object.entries(nameMap)) {
    if (name === message.sender) {
      return id;
    }
  }
  return null;
}
