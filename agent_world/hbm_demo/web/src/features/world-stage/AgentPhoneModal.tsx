import { useCallback, useMemo, useState } from "react";
import type { GameMessage, LocationChange, StateChange } from "../../api/types";
import { agentDisplayName } from "../../constants/agents";
import type { AgentInbox } from "../../store/worldSync";
import { AgentContactList } from "./AgentContactList";
import { AgentThreadDetail } from "./AgentThreadDetail";
import {
  buildContactThreads,
  type ContactThread,
} from "./agentContactThreads";

export interface AgentPhoneModalProps {
  agentId: string;
  inbox: AgentInbox;
  nameMap: Record<string, string>;
  onClose: () => void;
  onOpenPromptTrace?: (req: {
    refKey?: string;
    label?: string;
    noPromptReason?: string;
  }) => void;
}

export function AgentPhoneModal({
  agentId,
  inbox,
  nameMap,
  onClose,
  onOpenPromptTrace,
}: AgentPhoneModalProps) {
  const [activeThread, setActiveThread] = useState<ContactThread | null>(null);
  const title = agentDisplayName(agentId, nameMap);
  const threads = useMemo(
    () => buildContactThreads(inbox, nameMap, agentId),
    [inbox, nameMap, agentId],
  );

  const openMessageTrace = useCallback(
    (message: GameMessage) => {
      onOpenPromptTrace?.({
        refKey: message.ref_key,
        label: `${title} · ${message.type} @ t=${message.attempted_at ?? "?"}`,
      });
    },
    [onOpenPromptTrace, title],
  );

  const openStateTrace = useCallback(
    (entry: StateChange) => {
      onOpenPromptTrace?.({
        refKey: entry.ref_key,
        label: `${title} · OS @ t=${entry.at_tick}`,
      });
    },
    [onOpenPromptTrace, title],
  );

  const openLocationTrace = useCallback(
    (entry: LocationChange) => {
      if (entry.source === "ipc_move") {
        onOpenPromptTrace?.({
          label: `${title} · 地点 @ t=${entry.at_tick}`,
          noPromptReason: "系统移动（IPC 路由）· 无 LLM Prompt",
        });
        return;
      }
      onOpenPromptTrace?.({
        refKey: entry.ref_key,
        label: `${title} · 地点 @ t=${entry.at_tick}`,
      });
    },
    [onOpenPromptTrace, title],
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
              onPromptMessage={openMessageTrace}
              onPromptState={openStateTrace}
              onPromptLocation={openLocationTrace}
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
