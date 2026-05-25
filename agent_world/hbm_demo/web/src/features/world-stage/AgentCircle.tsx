import type { CSSProperties } from "react";
import { agentDisplayName, PLAYER_AGENT_ID } from "../../constants/agents";
import { moveKeyForAgent } from "../../store/worldSync";

export interface AgentCircleProps {
  agentId: string;
  index: number;
  total: number;
  nameMap: Record<string, string>;
  recentMoveKeys: string[];
  onClick: (agentId: string) => void;
}

function offsetStyle(index: number, total: number): CSSProperties {
  if (total <= 1) {
    return { left: "50%", top: "58%" };
  }
  const angle = Math.PI + (index / Math.max(total - 1, 1)) * Math.PI;
  const radius = Math.min(28, 18 + total * 2);
  const x = 50 + Math.cos(angle) * radius * 0.35;
  const y = 58 + Math.sin(angle) * radius * 0.22;
  return { left: `${x}%`, top: `${y}%` };
}

/** Agent 圆点 — click 打开手机面板；移动时 fade-in（dev_logs/32 §6.4 方案 B）。 */
export function AgentCircle({
  agentId,
  index,
  total,
  nameMap,
  recentMoveKeys,
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
      ]
        .filter(Boolean)
        .join(" ")}
      style={offsetStyle(index, total)}
      title={label}
      aria-label={label}
      onClick={() => {
        if (!isPlayer) {
          onClick(agentId);
        }
      }}
      disabled={isPlayer}
    >
      <span className="agent-circle__dot" />
      <span className="agent-circle__label">{label}</span>
    </button>
  );
}
