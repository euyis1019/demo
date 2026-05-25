import type { GameMessage } from "../../api/types";
import { isPlayerSender } from "../../utils/messages";

export interface RoomSpeechBubbleProps {
  messages: GameMessage[];
}

/** 房间内 F2F 短气泡 — 最近 3 条（dev_logs/32 §6.3）。 */
export function RoomSpeechBubble({ messages }: RoomSpeechBubbleProps) {
  const recent = messages.slice(-3);
  if (recent.length === 0) {
    return null;
  }

  return (
    <div className="room-speech-layer" aria-live="polite">
      {recent.map((message, index) => {
        const player = isPlayerSender(message.sender);
        return (
          <div
            key={`${message.attempted_at ?? index}-${message.sender}-${message.content.slice(0, 24)}`}
            className={[
              "room-speech-bubble",
              player ? "room-speech-bubble--player" : "room-speech-bubble--npc",
            ].join(" ")}
          >
            <span className="room-speech-bubble__sender">{message.sender}</span>
            <span className="room-speech-bubble__text">{message.content}</span>
          </div>
        );
      })}
    </div>
  );
}
