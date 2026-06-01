export interface AgentEphemeralBubbleProps {
  content: string;
}

/** Short-lived speech bubble anchored to an agent circle (top-right). */
export function AgentEphemeralBubble({ content }: AgentEphemeralBubbleProps) {
  const text = content.length > 48 ? `${content.slice(0, 48)}…` : content;

  return (
    <span className="agent-ephemeral-bubble" role="status" aria-live="polite">
      {text}
    </span>
  );
}
