import type { GameMessage } from "../api/types";

export interface MessageLineProps {
  message: GameMessage;
  /** F2F：玩家气泡靠右 */
  variant?: "f2f" | "rdc" | "grp";
}

const TERMINAL_SENDER = "彭博终端";

function isPlayer(sender: string): boolean {
  return sender === "玩家" || sender === "Player";
}

/** 单行消息（F4 将升级为 MessageBubble）。 */
export function MessageLine({ message, variant = "f2f" }: MessageLineProps) {
  const player = variant === "f2f" && isPlayer(message.sender);
  const terminal = message.sender === TERMINAL_SENDER;

  return (
    <article
      className={[
        "msg-line",
        `msg-line--${variant}`,
        player ? "msg-line--player" : "msg-line--npc",
        terminal ? "msg-line--terminal" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <header className="msg-line__header">
        {variant === "rdc" && message.recipient ? (
          <span className="msg-line__route">
            {message.sender} → {message.recipient}
          </span>
        ) : (
          <span className="msg-line__sender">{message.sender}</span>
        )}
        {variant === "grp" && message.group_id !== undefined ? (
          <span className="msg-line__group">GRP #{message.group_id}</span>
        ) : null}
      </header>
      <p className="msg-line__content">{message.content}</p>
    </article>
  );
}
