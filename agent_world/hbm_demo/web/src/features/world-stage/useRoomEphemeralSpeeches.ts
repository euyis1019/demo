import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { GameMessage } from "../../api/types";
import { messageKey } from "../../utils/messages";
import { resolveSpeakerAgentId } from "./resolveSpeakerAgentId";

export interface EphemeralSpeech {
  content: string;
  key: string;
}

const SPEECH_VISIBLE_MS = 5200;

function showSpeech(
  speakerId: string,
  content: string,
  dedupeKey: string,
  setSpeeches: Dispatch<SetStateAction<Record<string, EphemeralSpeech>>>,
): () => void {
  setSpeeches((prev) => ({
    ...prev,
    [speakerId]: { content, key: dedupeKey },
  }));

  const timer = window.setTimeout(() => {
    setSpeeches((prev) => {
      if (prev[speakerId]?.key !== dedupeKey) {
        return prev;
      }
      const next = { ...prev };
      delete next[speakerId];
      return next;
    });
  }, SPEECH_VISIBLE_MS);

  return () => window.clearTimeout(timer);
}

/** Track short-lived speech bubbles on agent circles when new F2F arrives. */
export function useRoomEphemeralSpeeches(
  messages: GameMessage[],
  agentsInRoom: string[],
  nameMap: Record<string, string>,
): Record<string, EphemeralSpeech> {
  const [speeches, setSpeeches] = useState<Record<string, EphemeralSpeech>>({});
  const seenKeysRef = useRef<Set<string>>(new Set());
  const prevLenRef = useRef(0);

  useEffect(() => {
    const cleanups: Array<() => void> = [];

    if (prevLenRef.current === 0 && messages.length > 0) {
      for (const message of messages) {
        seenKeysRef.current.add(messageKey(message));
      }
      prevLenRef.current = messages.length;
      return undefined;
    }

    if (messages.length <= prevLenRef.current) {
      prevLenRef.current = messages.length;
      return undefined;
    }

    for (let index = prevLenRef.current; index < messages.length; index += 1) {
      const message = messages[index];
      const dedupeKey = messageKey(message);
      if (seenKeysRef.current.has(dedupeKey)) {
        continue;
      }
      seenKeysRef.current.add(dedupeKey);

      const speakerId = resolveSpeakerAgentId(message, nameMap);
      if (!speakerId || !agentsInRoom.includes(speakerId)) {
        continue;
      }

      cleanups.push(
        showSpeech(speakerId, message.content, dedupeKey, setSpeeches),
      );
    }

    prevLenRef.current = messages.length;

    return () => {
      for (const cleanup of cleanups) {
        cleanup();
      }
    };
  }, [messages, agentsInRoom, nameMap]);

  return speeches;
}
