import type { PlaceId } from "../../utils/places";
import { ROOM_GRID } from "../../utils/places";
import { PLAYER_AGENT_ID } from "../../constants/agents";

const PLACE_BACKGROUNDS: Record<PlaceId, string> = {
  nvidia_reception: "/assets/story/places/nvidia_reception_bg.webp",
  jensen_private_room: "/assets/story/places/jensen_private_room_bg.webp",
  negotiation_room: "/assets/story/places/negotiation_room_bg.webp",
  openai_hq: "/assets/story/places/openai_hq_bg.webp",
};

export function storyPlaceBackground(placeId: string): string {
  if (ROOM_GRID.includes(placeId as PlaceId)) {
    return PLACE_BACKGROUNDS[placeId as PlaceId];
  }
  return PLACE_BACKGROUNDS.nvidia_reception;
}

/** Avatar for subtitle strip — agent id or ``player`` (pre-keyed PNG). */
export function storyAvatarUrl(speakerId: string): string {
  if (speakerId === PLAYER_AGENT_ID) {
    return "/assets/story/avatars/player.png";
  }
  return `/assets/story/avatars/agent_${speakerId}.png`;
}
