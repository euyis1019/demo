import type { RdcLink } from "../../../store/worldSync";
import { agentGridCenter } from "../lib/agentCircleLayout";

export interface RdcConnectionOverlayProps {
  links: RdcLink[];
  agentLocations: Record<string, { placeId: string; arrivedAt: number }>;
  places: string[];
  cols: number;
  rows: number;
}

/** Dashed lines between RDC sender and recipient agent circles. */
export function RdcConnectionOverlay({
  links,
  agentLocations,
  places,
  cols,
  rows,
}: RdcConnectionOverlayProps) {
  const segments = links
    .map((link) => {
      const from = agentGridCenter(link.from, agentLocations, places, cols, rows);
      const to = agentGridCenter(link.to, agentLocations, places, cols, rows);
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
