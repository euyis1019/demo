import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GameMessage } from "../../api/types";
import { agentDisplayName } from "../../constants/agents";
import { sortMessages } from "../../utils/messages";
import type { PlaceId } from "../../utils/places";
import { resolveSpeakerAgentId } from "../world-stage";
import { storyAvatarBaseUrl, storyAvatarUrl } from "./storyAssets";

export interface StoryDialogueLine {
  message: GameMessage;
  speakerId: string;
  speakerName: string;
  avatarUrl: string;
  /** 基础立绘 URL，供情绪变体图缺失时回退。 */
  avatarFallbackUrl: string;
}

function buildLine(
  message: GameMessage | undefined,
  nameMap: Record<string, string>,
  agentMood: Record<string, string> = {},
): StoryDialogueLine | null {
  if (!message) {
    return null;
  }
  const speakerId = resolveSpeakerAgentId(message, nameMap) ?? "1";
  // 立绘情绪优先用「这句台词」的情绪(每句都刷新)，无则回退该 agent 最新 OS 情绪(agentMood)。
  const mood = message.emotion || agentMood[speakerId];
  return {
    message,
    speakerId,
    speakerName: agentDisplayName(speakerId, nameMap),
    avatarUrl: storyAvatarUrl(speakerId, mood),
    avatarFallbackUrl: storyAvatarBaseUrl(speakerId),
  };
}

export function useStoryDialogue(
  roomMessages: GameMessage[] | undefined,
  nameMap: Record<string, string>,
  agentMood: Record<string, string> = {},
): StoryDialogueLine | null {
  return useMemo(() => {
    const sorted = sortMessages(roomMessages ?? []);
    return buildLine(sorted.at(-1), nameMap, agentMood);
  }, [roomMessages, nameMap, agentMood]);
}

export interface StoryDialogueQueue {
  /** Line currently shown in the subtitle. */
  line: StoryDialogueLine | null;
  /** True when there are unread lines after the current one. */
  hasNext: boolean;
  /** Number of unread lines after the current cursor. */
  remaining: number;
  /** Advance the cursor one line toward the latest message. */
  advance: () => void;
}

/**
 * Subtitle as a per-tick step-through queue. The strip shows one line at a
 * time, so within a single tick several agents speaking would flash past. The
 * cursor steps through *the latest tick's* lines on click; the moment a newer
 * tick arrives the subtitle jumps to it (cursor resets to that tick's first
 * line) so the player stays synced with the live world instead of crawling
 * through a growing cross-tick backlog. Everything is preserved in the side
 * history panel regardless, so jumping ticks never loses information.
 */
export function useStoryDialogueQueue(
  roomMessages: GameMessage[] | undefined,
  nameMap: Record<string, string>,
  agentMood: Record<string, string> = {},
): StoryDialogueQueue {
  const sorted = useMemo(() => sortMessages(roomMessages ?? []), [roomMessages]);

  // The latest tick present (max attempted_at); its messages are the step-set.
  const latestTick = useMemo(
    () => (sorted.length ? (sorted[sorted.length - 1].attempted_at ?? 0) : null),
    [sorted],
  );
  const tickMessages = useMemo(
    () =>
      latestTick == null
        ? []
        : sorted.filter((m) => (m.attempted_at ?? 0) === latestTick),
    [sorted, latestTick],
  );

  const [cursor, setCursor] = useState(0);
  const focusedTickRef = useRef<number | null>(null);

  useEffect(() => {
    if (latestTick == null) {
      focusedTickRef.current = null;
      setCursor(0);
      return;
    }
    if (focusedTickRef.current !== latestTick) {
      // A newer tick arrived → jump to it and show its first line. Keeps the
      // subtitle live rather than letting the player fall behind the sim.
      focusedTickRef.current = latestTick;
      setCursor(0);
      return;
    }
    // Same tick, more same-tick lines may have streamed in → hold, just clamp.
    setCursor((c) => Math.min(c, Math.max(0, tickMessages.length - 1)));
  }, [latestTick, tickMessages.length]);

  const safeCursor = Math.min(cursor, Math.max(0, tickMessages.length - 1));
  const line = useMemo(
    () => buildLine(tickMessages[safeCursor], nameMap, agentMood),
    [tickMessages, safeCursor, nameMap, agentMood],
  );
  const remaining = Math.max(0, tickMessages.length - 1 - safeCursor);
  const advance = useCallback(() => {
    setCursor((c) => Math.min(c + 1, Math.max(0, tickMessages.length - 1)));
  }, [tickMessages.length]);

  return { line, hasNext: remaining > 0, remaining, advance };
}

export function playerRoomMessages(
  roomF2f: Record<PlaceId, GameMessage[]>,
  placeId: string,
): GameMessage[] {
  return roomF2f[placeId as PlaceId] ?? [];
}
