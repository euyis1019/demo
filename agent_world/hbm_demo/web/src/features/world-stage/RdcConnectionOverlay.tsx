import type { RdcLink } from "../../store/worldSync";
import { agentGridCenter } from "./agentCircleLayout";

export interface RdcConnectionOverlayProps {
  links: RdcLink[];
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
}

/** Dashed lines between RDC sender and recipient agent circles. */
export function RdcConnectionOverlay({ links, agentLocations }: RdcConnectionOverlayProps) {
  const segments = links
    .map((link) => {
      const from = agentGridCenter(link.from, agentLocations);
      const to = agentGridCenter(link.to, agentLocations);
      if (!from || !to) {
        return null;
      }
      return { key: link.key, from, to };
    })
    .filter((segment): segment is NonNullable<typeof segment> => segment != null);

  if (segments.length === 0) {
    return null;
  }

  return (
    <svg
      className="rdc-connection-layer"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden
    >
      {segments.map((segment) => (
        <line
          key={segment.key}
          className="rdc-connection-line"
          x1={segment.from.x}
          y1={segment.from.y}
          x2={segment.to.x}
          y2={segment.to.y}
        />
      ))}
    </svg>
  );
}
