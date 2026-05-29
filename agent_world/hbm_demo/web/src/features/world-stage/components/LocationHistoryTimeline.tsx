import type { LocationChange } from "../../../api/types";
import { placeDisplayName } from "../../../utils/places";

export interface LocationHistoryTimelineProps {
  entries: LocationChange[];
  onPromptClick?: (entry: LocationChange) => void;
}

function sourceLabel(source: string): string {
  if (source === "ipc_move") {
    return "系统安排";
  }
  if (source === "request_move") {
    return "自主移动";
  }
  if (source === "script") {
    return "剧本";
  }
  return source;
}

export function LocationHistoryTimeline({
  entries,
  onPromptClick,
}: LocationHistoryTimelineProps) {
  if (entries.length === 0) {
    return <p className="agent-phone__empty">暂无地点变更记录</p>;
  }

  return (
    <ol className="location-history-timeline">
      {entries.map((entry) => {
        const fromLabel = entry.from_place
          ? placeDisplayName(entry.from_place)
          : "—";
        const toLabel = placeDisplayName(entry.to_place);
        const canPrompt =
          entry.source !== "ipc_move" &&
          Boolean(entry.ref_key || entry.prompt_trace_id);

        return (
          <li
            key={`${entry.at_tick}-${entry.from_place}-${entry.to_place}`}
            className="location-history-timeline__item"
          >
            <span className="location-history-timeline__tick">t={entry.at_tick}</span>
            <span className="location-history-timeline__text">
              {sourceLabel(entry.source)} · {fromLabel} → {toLabel}
            </span>
            {entry.source === "ipc_move" ? (
              <span className="location-history-timeline__hint">系统移动 · 无 Prompt</span>
            ) : canPrompt && onPromptClick ? (
              <button
                type="button"
                className="prompt-trace-btn"
                title="查看 Prompt"
                onClick={() => onPromptClick(entry)}
              >
                📝
              </button>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
