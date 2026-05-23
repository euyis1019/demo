import type { ReactNode } from "react";
import type { GameMessage } from "../api/types";
import { MessageLine } from "./MessageLine";

export interface MainChatProps {
  messages: GameMessage[];
  immediateMsg?: string;
  children?: ReactNode;
}

/** F2-3 — 中屏 F2F 对话 + immediate_msg 斜体灰字占位（F3 接 API）。 */
export function MainChat({ messages, immediateMsg, children }: MainChatProps) {
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
              <MessageLine
                key={`${msg.sender}-${msg.attempted_at ?? index}-${index}`}
                message={msg}
                variant="f2f"
              />
            ))
          )}
          {immediateMsg ? (
            <p className="main-chat__immediate">{immediateMsg}</p>
          ) : null}
        </div>
        {children ? <div className="main-chat__input">{children}</div> : null}
      </div>
    </>
  );
}
