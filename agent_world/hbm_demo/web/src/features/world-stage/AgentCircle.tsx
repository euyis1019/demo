import { agentDisplayName, PLAYER_AGENT_ID } from "../../constants/agents";
import { moveKeyForAgent } from "../../store/worldSync";
import { cellLocalStyle } from "./agentCircleLayout";
import { AgentEphemeralBubble } from "./AgentEphemeralBubble";

export interface AgentCircleProps {
  agentId: string;
  index: number;
  total: number;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  speechContent?: string;
  onClick: (agentId: string) => void;
}

/** Agent 圆点 — click 打开手机面板；移动时 fade-in；F2F 说话时右上角 ephemeral 气泡。 */
export function AgentCircle({
  agentId,
  index,
  total,
  nameMap,
  recentMoveKeys,
  speechContent,
  onClick,
}: AgentCircleProps) {
  const isPlayer = agentId === PLAYER_AGENT_ID;
  const moving = moveKeyForAgent(agentId, recentMoveKeys);
  const label = agentDisplayName(agentId, nameMap);

  return (
    <button
      type="button"
      className={[
        "agent-circle",
        isPlayer ? "agent-circle--player" : "agent-circle--npc",
        moving ? "agent-circle--moving" : "",
        speechContent ? "agent-circle--speaking" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={cellLocalStyle(index, total)}
      title={label}
      aria-label={label}
      onClick={() => {
        if (!isPlayer) {
          onClick(agentId);
        }
      }}
      disabled={isPlayer}
    >
      <span className="agent-circle__body">
        <span className="agent-circle__dot" />
        {speechContent ? <AgentEphemeralBubble content={speechContent} /> : null}
      </span>
      <span className="agent-circle__label">{label}</span>
    </button>
  );
}
