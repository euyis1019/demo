import type { GameMessage } from "../../api/types";
import { groupDisplayLabel } from "../../constants/groups";
import { isChatSelfMessage } from "../../utils/chatLayout";
import { TERMINAL_SENDER } from "../../utils/messages";

export type MessageBubbleVariant = "f2f" | "rdc" | "grp";

export interface MessageBubbleProps {
  message: GameMessage;
  variant?: MessageBubbleVariant;
  /** Player id or agent id — with chatLayout, self messages align right. */
  inboxOwnerId?: string;
  chatLayout?: boolean;
  nameMap?: Record<string, string>;
  onPromptClick?: (message: GameMessage) => void;
}

/** F4 — chat bubbles; with chatLayout: left = peer, right = self (WeChat). */
export function MessageBubble({
  message,
  variant = "f2f",
  inboxOwnerId,
  chatLayout = false,
  nameMap,
  onPromptClick,
}: MessageBubbleProps) {
  const terminal =
    message.sender === TERMINAL_SENDER ||
    message.sender === "系统" ||
    message.sender === "彭博终端" ||
    message.is_system;

  const chatSelf =
    chatLayout &&
    inboxOwnerId != null &&
    isChatSelfMessage(message, inboxOwnerId, nameMap);
  const player = chatLayout ? chatSelf : variant === "f2f" && isChatSelfMessage(message, "player", nameMap);

  const groupLabel =
    variant === "grp" && !chatLayout ? groupDisplayLabel(message.group_id) : undefined;

  const showSenderHeader = !chatLayout || terminal || (chatLayout && !chatSelf);

  const showPrompt =
    Boolean(onPromptClick) &&
    Boolean(message.ref_key || message.prompt_trace_id) &&
    !terminal;

  return (
    <article
      className={[
        "msg-bubble",
        `msg-bubble--${variant}`,
        player ? "msg-bubble--player" : "msg-bubble--npc",
        terminal ? "msg-bubble--terminal" : "",
        chatLayout ? "msg-bubble--chat" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {showSenderHeader ? (
        <header className="msg-bubble__header">
          {variant === "rdc" && message.recipient && !chatLayout ? (
            <span className="msg-bubble__route">
              {message.sender} → {message.recipient}
            </span>
          ) : (
            <span className="msg-bubble__sender">
              {terminal ? "系统" : message.sender}
            </span>
          )}
          {groupLabel ? (
            <span className="msg-bubble__group" title={`group_id=${message.group_id}`}>
              {groupLabel}
            </span>
          ) : null}
          {showPrompt ? (
            <button
              type="button"
              className="prompt-trace-btn msg-bubble__prompt"
              title="查看 Prompt"
              onClick={() => onPromptClick?.(message)}
            >
              📝
            </button>
          ) : null}
        </header>
      ) : showPrompt ? (
        <div className="msg-bubble__header msg-bubble__header--prompt-only">
          <button
            type="button"
            className="prompt-trace-btn msg-bubble__prompt"
            title="查看 Prompt"
            onClick={() => onPromptClick?.(message)}
          >
            📝
          </button>
        </div>
      ) : null}
      <p className="msg-bubble__content">{message.content}</p>
    </article>
  );
}
