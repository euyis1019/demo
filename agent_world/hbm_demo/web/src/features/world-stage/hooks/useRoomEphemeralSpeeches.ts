import { useEffect, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { GameMessage } from "../../../api/types";
import { messageKey } from "../../../utils/messages";
import { resolveSpeakerAgentId } from "../lib/resolveSpeakerAgentId";

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
  timersRef: MutableRefObject<Map<string, number>>,
): void {
  setSpeeches((prev) => ({
    ...prev,
    [speakerId]: { content, key: dedupeKey },
  }));

  const prevTimer = timersRef.current.get(dedupeKey);
  if (prevTimer != null) {
    window.clearTimeout(prevTimer);
  }

  const timer = window.setTimeout(() => {
    timersRef.current.delete(dedupeKey);
    setSpeeches((prev) => {
      if (prev[speakerId]?.key !== dedupeKey) {
        return prev;
      }
      const next = { ...prev };
      delete next[speakerId];
      return next;
    });
  }, SPEECH_VISIBLE_MS);

  timersRef.current.set(dedupeKey, timer);
}

function latestSpeechesByAgent(
  messages: GameMessage[],
  agentsInRoom: string[],
  nameMap: Record<string, string>,
): Array<{ speakerId: string; message: GameMessage; dedupeKey: string }> {
  const latestByAgent = new Map<
    string,
    { speakerId: string; message: GameMessage; dedupeKey: string }
  >();

  for (const message of messages) {
    const speakerId = resolveSpeakerAgentId(message, nameMap);
    if (!speakerId || !agentsInRoom.includes(speakerId)) {
      continue;
    }
    latestByAgent.set(speakerId, {
      speakerId,
      message,
      dedupeKey: messageKey(message),
    });
  }

  return [...latestByAgent.values()];
}

/** Track short-lived speech bubbles on agent circles when new F2F arrives. */
export function useRoomEphemeralSpeeches(
  messages: GameMessage[],
  agentsInRoom: string[],
  nameMap: Record<string, string>,
): Record<string, EphemeralSpeech> {
  const [speeches, setSpeeches] = useState<Record<string, EphemeralSpeech>>({});
  const seenKeysRef = useRef<Set<string>>(new Set());
  const initializedRef = useRef(false);
  const timersRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    return () => {
      for (const timer of timersRef.current.values()) {
        window.clearTimeout(timer);
      }
      timersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (!initializedRef.current) {
      if (messages.length === 0) {
        return;
      }
      for (const { speakerId, message, dedupeKey } of latestSpeechesByAgent(
        messages,
        agentsInRoom,
        nameMap,
      )) {
        seenKeysRef.current.add(dedupeKey);
        showSpeech(speakerId, message.content, dedupeKey, setSpeeches, timersRef);
      }
      for (const message of messages) {
        seenKeysRef.current.add(messageKey(message));
      }
      initializedRef.current = true;
      return;
    }

    for (const message of messages) {
      const dedupeKey = messageKey(message);
      if (seenKeysRef.current.has(dedupeKey)) {
        continue;
      }
      seenKeysRef.current.add(dedupeKey);

      const speakerId = resolveSpeakerAgentId(message, nameMap);
      if (!speakerId || !agentsInRoom.includes(speakerId)) {
        continue;
      }

      showSpeech(speakerId, message.content, dedupeKey, setSpeeches, timersRef);
    }
  }, [messages, agentsInRoom, nameMap]);

  return speeches;
}
