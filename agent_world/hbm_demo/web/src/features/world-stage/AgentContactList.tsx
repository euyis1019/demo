import type { ContactThread } from "./agentContactThreads";

export interface AgentContactListProps {
  threads: ContactThread[];
  onSelect: (thread: ContactThread) => void;
}

export function AgentContactList({ threads, onSelect }: AgentContactListProps) {
  if (threads.length === 0) {
    return <p className="agent-phone__empty">暂无联系人或消息</p>;
  }

  return (
    <ul className="agent-contact-list">
      {threads.map((thread) => (
        <li key={thread.key}>
          <button
            type="button"
            className={[
              "agent-contact-list__item",
              thread.archived ? "agent-contact-list__item--archived" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => onSelect(thread)}
          >
            <span
              className={[
                "agent-contact-list__avatar",
                `agent-contact-list__avatar--${thread.kind}`,
              ].join(" ")}
              aria-hidden
            >
              {thread.kind === "rdc" ? "私" : thread.kind === "grp" ? "群" : thread.kind === "f2f" ? "面" : "OS"}
            </span>
            <span className="agent-contact-list__main">
              <span className="agent-contact-list__title-row">
                <span className="agent-contact-list__title">{thread.title}</span>
                {thread.archived ? (
                  <span className="agent-contact-list__badge">已归档</span>
                ) : null}
              </span>
              <span className="agent-contact-list__preview">{thread.preview}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
