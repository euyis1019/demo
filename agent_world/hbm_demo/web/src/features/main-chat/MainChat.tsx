import type { ReactNode } from "react";
import type { GameMessage } from "../../api/types";
import { useAutoScroll } from "../shared/useAutoScroll";
import { messageReactKey } from "../../utils/messages";
import { MessageBubble } from "./MessageBubble";

export interface MainChatProps {
  messages: GameMessage[];
  immediateMsg?: string;
  children?: ReactNode;
}

/** F2-3 + F4-3 — F2F 消息列表、immediate_msg、自动滚动。 */
export function MainChat({ messages, immediateMsg, children }: MainChatProps) {
  const scrollAnchorRef = useAutoScroll([messages.length, immediateMsg]);

  return (
    <>
      <div className="panel__header panel__header--main">
        <span>Main Chat</span>
        <span className="panel__header-hint">F2F · 公开对话</span>
      </div>
      <div className="panel__body main-chat">
        <div className="main-chat__scroll" role="log" aria-live="polite">
          {messages.length === 0 ? (
            <p className="main-chat__empty">暂无公开对话，发送第一条消息开始谈判。</p>
          ) : (
            messages.map((msg, index) => (
              <MessageBubble
                key={messageReactKey(msg, index)}
                message={msg}
                variant="f2f"
              />
            ))
          )}
          {immediateMsg ? (
            <p className="main-chat__immediate">{immediateMsg}</p>
          ) : null}
          <div ref={scrollAnchorRef} className="scroll-anchor" aria-hidden="true" />
        </div>
        {children ? <div className="main-chat__input">{children}</div> : null}
      </div>
    </>
  );
}
