import type { GameMessage } from "../api/types";
import { groupDisplayLabel } from "../constants/groups";
import { isPlayerSender, TERMINAL_SENDER } from "../utils/messages";

export type MessageBubbleVariant = "f2f" | "rdc" | "grp";

export interface MessageBubbleProps {
  message: GameMessage;
  variant?: MessageBubbleVariant;
}

/** F4-1/F4-2 — F2F 左 NPC / 右玩家；RDC 路由；GRP 群标签。 */
export function MessageBubble({
  message,
  variant = "f2f",
}: MessageBubbleProps) {
  const player = variant === "f2f" && isPlayerSender(message.sender);
  const terminal =
    message.sender === TERMINAL_SENDER ||
    message.sender === "系统" ||
    message.sender === "彭博终端";

  const groupLabel =
    variant === "grp" ? groupDisplayLabel(message.group_id) : undefined;

  return (
    <article
      className={[
        "msg-bubble",
        `msg-bubble--${variant}`,
        player ? "msg-bubble--player" : "msg-bubble--npc",
        terminal ? "msg-bubble--terminal" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <header className="msg-bubble__header">
        {variant === "rdc" && message.recipient ? (
          <span className="msg-bubble__route">
            {message.sender} → {message.recipient}
          </span>
        ) : (
          <span className="msg-bubble__sender">{message.sender}</span>
        )}
        {groupLabel ? (
          <span className="msg-bubble__group" title={`group_id=${message.group_id}`}>
            {groupLabel}
          </span>
        ) : null}
      </header>
      <p className="msg-bubble__content">{message.content}</p>
    </article>
  );
}
