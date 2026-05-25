import { useState } from "react";
import { agentDisplayName } from "../../constants/agents";
import type { AgentInbox } from "../../store/worldSync";
import { InnerOsTimeline } from "./InnerOsTimeline";
import { MessageThreadList } from "./MessageThreadList";

export interface AgentPhoneModalProps {
  agentId: string;
  inbox: AgentInbox;
  nameMap: Record<string, string>;
  onClose: () => void;
}

type PhoneTab = "rdc" | "grp" | "os";

export function AgentPhoneModal({
  agentId,
  inbox,
  nameMap,
  onClose,
}: AgentPhoneModalProps) {
  const [tab, setTab] = useState<PhoneTab>("rdc");
  const title = agentDisplayName(agentId, nameMap);

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="agent-phone-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${title} 手机消息`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="agent-phone-modal__header">
          <div>
            <h2>{title}</h2>
            <p className="agent-phone-modal__subtitle">Agent #{agentId}</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="agent-phone-tabs" role="tablist">
          {(
            [
              ["rdc", "私信"],
              ["grp", "群聊"],
              ["os", "内心 OS"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={[
                "agent-phone-tabs__btn",
                tab === id ? "agent-phone-tabs__btn--active" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="agent-phone-modal__body">
          {tab === "rdc" ? <MessageThreadList inbox={inbox} kind="rdc" /> : null}
          {tab === "grp" ? <MessageThreadList inbox={inbox} kind="grp" /> : null}
          {tab === "os" ? <InnerOsTimeline entries={inbox.osLog} /> : null}
        </div>
      </div>
    </div>
  );
}
