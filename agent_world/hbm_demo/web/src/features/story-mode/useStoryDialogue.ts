import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GameMessage } from "../../api/types";
import { agentDisplayName } from "../../constants/agents";
import { messageKey, sortMessages } from "../../utils/messages";
import type { PlaceId } from "../../utils/places";
import { resolveSpeakerAgentId } from "../world-stage/resolveSpeakerAgentId";
import { storyAvatarUrl, storyPortraitUrl } from "./storyAssets";

export interface StoryDialogueLine {
  message: GameMessage;
  speakerId: string;
  speakerName: string;
  avatarUrl: string;
  portraitUrl: string;
  pose: string;
}

function toDialogueLine(
  message: GameMessage,
  nameMap: Record<string, string>,
): StoryDialogueLine {
  const speakerId = resolveSpeakerAgentId(message, nameMap) ?? "1";
  const pose = message.display_pose ?? "neutral";
  return {
    message,
    speakerId,
    speakerName: agentDisplayName(speakerId, nameMap),
    avatarUrl: storyAvatarUrl(speakerId),
    portraitUrl: storyPortraitUrl(speakerId, pose),
    pose,
  };
}

export function useStoryDialogueQueue(
  roomMessages: GameMessage[] | undefined,
  nameMap: Record<string, string>,
  resetKey: string,
): {
  line: StoryDialogueLine | null;
  pendingCount: number;
  advance: () => void;
} {
  const [current, setCurrent] = useState<GameMessage | null>(null);
  const [queue, setQueue] = useState<GameMessage[]>([]);
  const seenKeysRef = useRef<Set<string>>(new Set());
  const resetKeyRef = useRef(resetKey);

  useEffect(() => {
    if (resetKeyRef.current !== resetKey) {
      resetKeyRef.current = resetKey;
      seenKeysRef.current = new Set();
      setCurrent(null);
      setQueue([]);
    }
  }, [resetKey]);

  useEffect(() => {
    const incoming = sortMessages(roomMessages ?? []).filter((message) => {
      const key = messageKey(message);
      if (seenKeysRef.current.has(key)) {
        return false;
      }
      seenKeysRef.current.add(key);
      return true;
    });
    if (!incoming.length) {
      return;
    }
    setCurrent((prev) => {
      if (prev) {
        setQueue((old) => [...old, ...incoming]);
        return prev;
      }
      const [first, ...rest] = incoming;
      if (rest.length) {
        setQueue((old) => [...old, ...rest]);
      }
      return first;
    });
  }, [roomMessages]);

  const advance = useCallback(() => {
    setQueue((old) => {
      if (!old.length) {
        return old;
      }
      const [next, ...rest] = old;
      setCurrent(next);
      return rest;
    });
  }, []);

  const line = useMemo(
    () => (current ? toDialogueLine(current, nameMap) : null),
    [current, nameMap],
  );

  return { line, pendingCount: queue.length, advance };
}

export function playerRoomMessages(
  roomF2f: Record<PlaceId, GameMessage[]>,
  placeId: string,
): GameMessage[] {
  return roomF2f[placeId as PlaceId] ?? [];
}
