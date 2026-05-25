import type { ContactThread } from "./agentContactThreads";
import { MessageBubble } from "../main-chat/MessageBubble";
import { InnerOsTimeline } from "./InnerOsTimeline";

export interface AgentThreadDetailProps {
  thread: ContactThread;
  ownerAgentId: string;
  nameMap: Record<string, string>;
  onBack: () => void;
}

export function AgentThreadDetail({
  thread,
  ownerAgentId,
  nameMap,
  onBack,
}: AgentThreadDetailProps) {
  return (
    <div className="agent-thread-detail">
      <header className="agent-thread-detail__header">
        <button type="button" className="agent-thread-detail__back" onClick={onBack}>
          ← 返回
        </button>
        <h3 className="agent-thread-detail__title">{thread.title}</h3>
      </header>
      <div className="agent-thread-detail__body">
        {thread.kind === "os" ? (
          <InnerOsTimeline entries={thread.osEntries} />
        ) : (
          <div className="agent-thread-detail__messages chat-message-list">
            {thread.messages.map((message, index) => (
              <MessageBubble
                key={`${thread.key}-${index}`}
                message={message}
                variant={thread.kind === "grp" ? "grp" : "rdc"}
                inboxOwnerId={ownerAgentId}
                chatLayout
                nameMap={nameMap}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
