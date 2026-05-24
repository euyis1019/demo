import { useState } from "react";
import type { GameMessage } from "../../api/types";
import { useAutoScroll } from "../shared/useAutoScroll";
import { messageReactKey } from "../../utils/messages";
import { MessageBubble } from "../main-chat/MessageBubble";

export type ObserverTab = "rdc" | "grp";

export interface ObserverPanelProps {
  rdcMessages: GameMessage[];
  grpMessages: GameMessage[];
  currentTick?: number | null;
}

/** F2-4 + F4-3 — Tab RDC/GRP + auto-scroll。 */
export function ObserverPanel({
  rdcMessages,
  grpMessages,
  currentTick = null,
}: ObserverPanelProps) {
  const [tab, setTab] = useState<ObserverTab>("rdc");
  const messages = tab === "rdc" ? rdcMessages : grpMessages;
  const scrollAnchorRef = useAutoScroll([tab, messages.length]);

  return (
    <>
      <div className="panel__header observer-panel__header">
        <span>Observer</span>
        <div className="observer-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "rdc"}
            className={[
              "observer-tabs__btn",
              tab === "rdc" ? "observer-tabs__btn--active" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => setTab("rdc")}
          >
            私聊 RDC
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "grp"}
            className={[
              "observer-tabs__btn",
              tab === "grp" ? "observer-tabs__btn--active" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => setTab("grp")}
          >
            群聊 GRP
          </button>
        </div>
      </div>
      <div className="panel__body observer-panel">
        <div className="observer-panel__scroll" role="tabpanel">
          {messages.length === 0 ? (
            <p className="observer-panel__empty">
              {tab === "rdc" ? "暂无 RDC 私聊" : "暂无 GRP 群聊"}
            </p>
          ) : (
            messages.map((msg, index) => (
              <MessageBubble
                key={messageReactKey(msg, index)}
                message={msg}
                variant={tab}
              />
            ))
          )}
          <div ref={scrollAnchorRef} className="scroll-anchor" aria-hidden="true" />
        </div>
        <footer className="observer-panel__footer">
          {currentTick !== null ? (
            <span>World Tick · {currentTick}</span>
          ) : (
            <span className="observer-panel__footer-muted">env-status 不可用</span>
          )}
        </footer>
      </div>
    </>
  );
}
