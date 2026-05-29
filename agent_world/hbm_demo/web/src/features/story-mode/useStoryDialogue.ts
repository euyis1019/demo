import { useMemo } from "react";
import type { GameMessage } from "../../api/types";
import { agentDisplayName } from "../../constants/agents";
import { sortMessages } from "../../utils/messages";
import type { PlaceId } from "../../utils/places";
import { resolveSpeakerAgentId } from "../world-stage/lib/resolveSpeakerAgentId";
import { storyAvatarUrl } from "./storyAssets";

export interface StoryDialogueLine {
  message: GameMessage;
  speakerId: string;
  speakerName: string;
  avatarUrl: string;
}

export function useStoryDialogue(
  roomMessages: GameMessage[] | undefined,
  nameMap: Record<string, string>,
): StoryDialogueLine | null {
  return useMemo(() => {
    const sorted = sortMessages(roomMessages ?? []);
    const latest = sorted.at(-1);
    if (!latest) {
      return null;
    }
    const speakerId = resolveSpeakerAgentId(latest, nameMap) ?? "1";
    return {
      message: latest,
      speakerId,
      speakerName: agentDisplayName(speakerId, nameMap),
      avatarUrl: storyAvatarUrl(speakerId),
    };
  }, [roomMessages, nameMap]);
}

export function playerRoomMessages(
  roomF2f: Record<PlaceId, GameMessage[]>,
  placeId: string,
): GameMessage[] {
  return roomF2f[placeId as PlaceId] ?? [];
}
