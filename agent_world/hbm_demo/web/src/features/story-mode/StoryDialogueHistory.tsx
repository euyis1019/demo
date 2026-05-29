import { useEffect, useMemo, useRef, useState } from "react";
import type { GameMessage } from "../../api/types";
import { PLAYER_AGENT_ID, agentDisplayName } from "../../constants/agents";
import { messageReactKey, sortMessages, TERMINAL_SENDER } from "../../utils/messages";
import { placeDisplayName, type PlaceId } from "../../utils/places";
import { resolveSpeakerAgentId } from "../world-stage";

export interface StoryDialogueHistoryProps {
  /** Current-room F2F messages (already scoped to the player's place). */
  messages: GameMessage[];
  nameMap: Record<string, string>;
  placeId: PlaceId;
}

/**
 * Story-mode right-side dialogue log for the current room. The ADV subtitle
 * only shows the latest line; when several agents speak in one tick the player
 * misses earlier lines, so this scrollable panel keeps the full room history.
 * Semi-transparent glass styling (matches the story input) to preserve
 * immersion, and collapsible via a toggle so it never blocks the scene.
 */
export function StoryDialogueHistory({
  messages,
  nameMap,
  placeId,
}: StoryDialogueHistoryProps) {
  const [open, setOpen] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);

  const sorted = useMemo(() => sortMessages(messages), [messages]);

  // Keep the newest line in view as the conversation grows (and on reopen).
  useEffect(() => {
    if (!open) {
      return;
    }
    const el = listRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [open, sorted.length]);

  return (
    <>
      {!open ? (
        <button
          type="button"
          className="story-history__reopen"
          onClick={() => setOpen(true)}
          aria-label="显示对话记录"
          title="显示对话记录"
        >
          <span aria-hidden="true">💬</span>
          <span className="story-history__reopen-label">对话记录</span>
        </button>
      ) : null}

      <aside
        className={[
          "story-history",
          open ? "story-history--open" : "story-history--closed",
        ].join(" ")}
        aria-label={`${placeDisplayName(placeId)} 对话记录`}
        aria-hidden={!open}
      >
        <header className="story-history__header">
        <span className="story-history__title">
          对话记录 · {placeDisplayName(placeId)}
        </span>
        <button
          type="button"
          className="story-history__toggle"
          onClick={() => setOpen(false)}
          aria-label="隐藏对话记录"
          title="隐藏对话记录"
        >
          ×
        </button>
      </header>

      <div className="story-history__list" ref={listRef}>
        {sorted.length === 0 ? (
          <p className="story-history__empty">本房间暂无对话</p>
        ) : (
          sorted.map((message, index) => {
            const system =
              message.is_system || message.sender === TERMINAL_SENDER;
            const speakerId = resolveSpeakerAgentId(message, nameMap) ?? "1";
            const isPlayer = !system && speakerId === PLAYER_AGENT_ID;
            const speaker = system
              ? "系统"
              : agentDisplayName(speakerId, nameMap);

            return (
              <div
                key={messageReactKey(message, index)}
                className={[
                  "story-history__row",
                  system
                    ? "story-history__row--system"
                    : isPlayer
                      ? "story-history__row--player"
                      : "story-history__row--agent",
                ].join(" ")}
              >
                <span className="story-history__speaker">{speaker}</span>
                <span className="story-history__text">{message.content}</span>
              </div>
            );
          })
        )}
      </div>
      </aside>
    </>
  );
}
