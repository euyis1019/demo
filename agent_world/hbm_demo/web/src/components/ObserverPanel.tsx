import { useState } from "react";
import type { GameMessage } from "../api/types";
import { MessageLine } from "./MessageLine";

export type ObserverTab = "rdc" | "grp";

export interface ObserverPanelProps {
  rdcMessages: GameMessage[];
  grpMessages: GameMessage[];
}

/** F2-4 — Tab「私聊 RDC」「群聊 GRP」（dev_logs/03 右栏）。 */
export function ObserverPanel({ rdcMessages, grpMessages }: ObserverPanelProps) {
  const [tab, setTab] = useState<ObserverTab>("rdc");
  const messages = tab === "rdc" ? rdcMessages : grpMessages;

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
              <MessageLine
                key={`${tab}-${msg.sender}-${msg.attempted_at ?? index}-${index}`}
                message={msg}
                variant={tab}
              />
            ))
          )}
        </div>
      </div>
    </>
  );
}
