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

/** 基础立绘（一 agent 一张，无情绪维度）；玩家走 player.png。 */
export function storyAvatarBaseUrl(speakerId: string): string {
  if (speakerId === PLAYER_AGENT_ID) {
    return "/assets/story/avatars/player.png";
  }
  return `/assets/story/avatars/agent_${speakerId}.png`;
}

/**
 * 立绘 URL。给了非 neutral 情绪标签时返回情绪变体 `agent_{id}_{mood}.png`，
 * 缺该变体图时由 ChromaKeyAvatar 的 fallbackSrc 回退到基础立绘（见 storyAvatarBaseUrl）。
 */
export function storyAvatarUrl(speakerId: string, mood?: string): string {
  if (speakerId !== PLAYER_AGENT_ID && mood && mood !== "neutral") {
    return `/assets/story/avatars/agent_${speakerId}_${mood}.png`;
  }
  return storyAvatarBaseUrl(speakerId);
}
