import { PLAYER_AGENT_ID } from "../../constants/agents";

/** Avatar for subtitle strip — agent id or ``player`` (pre-keyed PNG). */
export function storyAvatarUrl(speakerId: string): string {
  if (speakerId === PLAYER_AGENT_ID) {
    return "/assets/story/avatars/player.png";
  }
  return `/assets/story/avatars/agent_${speakerId}.png`;
}
