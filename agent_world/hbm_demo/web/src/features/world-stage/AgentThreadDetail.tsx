import type { ContactThread } from "./agentContactThreads";
import type { GameMessage, LocationChange, StateChange } from "../../api/types";
import { MessageBubble } from "../shared/MessageBubble";
import { InnerOsTimeline } from "./InnerOsTimeline";
import { LocationHistoryTimeline } from "./LocationHistoryTimeline";

export interface AgentThreadDetailProps {
  thread: ContactThread;
  ownerAgentId: string;
  nameMap: Record<string, string>;
  onBack: () => void;
  onPromptMessage?: (message: GameMessage) => void;
  onPromptState?: (entry: StateChange) => void;
  onPromptLocation?: (entry: LocationChange) => void;
}

export function AgentThreadDetail({
  thread,
  ownerAgentId,
  nameMap,
  onBack,
  onPromptMessage,
  onPromptState,
  onPromptLocation,
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
          <InnerOsTimeline entries={thread.osEntries} onPromptClick={onPromptState} />
        ) : thread.kind === "location" ? (
          <LocationHistoryTimeline
            entries={thread.locationEntries}
            onPromptClick={onPromptLocation}
          />
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
                onPromptClick={onPromptMessage}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
