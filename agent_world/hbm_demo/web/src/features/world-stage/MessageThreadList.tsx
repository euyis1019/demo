import { useMemo } from "react";
import type { GameMessage } from "../../api/types";
import { groupDisplayLabel } from "../../constants/groups";
import { MessageBubble } from "../main-chat/MessageBubble";
import { threadKeyGrp, threadKeyRdc } from "../../store/worldSync";
import type { AgentInbox } from "../../store/worldSync";

export interface MessageThreadListProps {
  inbox: AgentInbox;
  kind: "rdc" | "grp";
  ownerAgentId: string;
  nameMap?: Record<string, string>;
}

interface ThreadGroup {
  key: string;
  label: string;
  messages: GameMessage[];
  archived: boolean;
}

function buildThreads(
  inbox: AgentInbox,
  kind: "rdc" | "grp",
  ownerAgentId: string,
): ThreadGroup[] {
  const messages = kind === "rdc" ? inbox.rdc : inbox.grp;
  const buckets = new Map<string, ThreadGroup>();

  for (const message of messages) {
    const key =
      kind === "rdc" ? threadKeyRdc(message, ownerAgentId) : threadKeyGrp(message);
    const label =
      kind === "grp"
        ? groupDisplayLabel(message.group_id) ?? key
        : message.recipient
          ? `${message.sender} ↔ ${message.recipient}`
          : message.sender;
    const existing = buckets.get(key);
    if (existing) {
      existing.messages.push(message);
    } else {
      buckets.set(key, {
        key,
        label,
        messages: [message],
        archived: inbox.archivedThreadKeys.includes(key),
      });
    }
  }

  return [...buckets.values()].sort((a, b) => {
    const aTick = a.messages.at(-1)?.attempted_at ?? 0;
    const bTick = b.messages.at(-1)?.attempted_at ?? 0;
    return aTick - bTick;
  });
}

export function MessageThreadList({
  inbox,
  kind,
  ownerAgentId,
  nameMap = {},
}: MessageThreadListProps) {
  const threads = useMemo(
    () => buildThreads(inbox, kind, ownerAgentId),
    [inbox, kind, ownerAgentId],
  );

  if (threads.length === 0) {
    return <p className="agent-phone__empty">暂无消息</p>;
  }

  return (
    <div className="message-thread-list">
      {threads.map((thread) => (
        <section
          key={thread.key}
          className={[
            "message-thread",
            thread.archived ? "message-thread--archived" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <header className="message-thread__header">
            <h4>{thread.label}</h4>
            {thread.archived ? (
              <span className="message-thread__badge">已归档</span>
            ) : null}
          </header>
          <div className="message-thread__messages chat-message-list">
            {thread.messages.map((message, index) => (
              <MessageBubble
                key={`${thread.key}-${index}`}
                message={message}
                variant={kind}
                inboxOwnerId={ownerAgentId}
                chatLayout
                nameMap={nameMap}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
