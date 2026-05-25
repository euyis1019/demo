import type { StateChange } from "../../api/types";

export interface InnerOsTimelineProps {
  entries: StateChange[];
}

export function InnerOsTimeline({ entries }: InnerOsTimelineProps) {
  if (entries.length === 0) {
    return <p className="agent-phone__empty">暂无内心 OS 记录</p>;
  }

  return (
    <ol className="inner-os-timeline">
      {entries.map((entry) => (
        <li key={`${entry.at_tick}-${entry.content.slice(0, 24)}`} className="inner-os-timeline__item">
          <span className="inner-os-timeline__tick">t={entry.at_tick}</span>
          <span className="inner-os-timeline__content">{entry.content}</span>
        </li>
      ))}
    </ol>
  );
}
