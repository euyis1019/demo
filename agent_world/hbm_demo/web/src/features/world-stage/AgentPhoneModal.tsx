import { useMemo, useState } from "react";
import { agentDisplayName } from "../../constants/agents";
import type { AgentInbox } from "../../store/worldSync";
import { buildContactThreads, type ContactThread } from "./agentContactThreads";
import { AgentContactList } from "./AgentContactList";
import { AgentThreadDetail } from "./AgentThreadDetail";

export interface AgentPhoneModalProps {
  agentId: string;
  inbox: AgentInbox;
  nameMap: Record<string, string>;
  onClose: () => void;
}

export function AgentPhoneModal({
  agentId,
  inbox,
  nameMap,
  onClose,
}: AgentPhoneModalProps) {
  const [activeThread, setActiveThread] = useState<ContactThread | null>(null);
  const title = agentDisplayName(agentId, nameMap);
  const threads = useMemo(
    () => buildContactThreads(inbox, nameMap, agentId),
    [inbox, nameMap, agentId],
  );

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
            <h2>{activeThread ? activeThread.title : title}</h2>
            <p className="agent-phone-modal__subtitle">
              {activeThread ? "对话详情" : `Agent #${agentId} · 联系人`}
            </p>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="agent-phone-modal__body">
          {activeThread ? (
            <AgentThreadDetail
              thread={activeThread}
              ownerAgentId={agentId}
              nameMap={nameMap}
              onBack={() => setActiveThread(null)}
            />
          ) : (
            <div className="agent-phone-modal__scroll">
              <AgentContactList threads={threads} onSelect={setActiveThread} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
