import { useEffect, useRef, useState } from "react";
import type { Stats } from "../../api/types";

export interface StoryStatsHudProps {
  stats: Stats;
  /** 故事张力 0–100（drama-manager 导演驱动）。 */
  tension?: number;
}

const ROWS: { key: keyof Stats; label: string }[] = [
  { key: "vision", label: "远见" },
  { key: "execution", label: "执行" },
  { key: "trust", label: "信任" },
  { key: "burnout", label: "倦怠" },
];

/**
 * 剧情模式数值 HUD（体检 G6）：把后端已下发的 stats 接到剧情模式（原先只有上帝模式显示）。
 * 数值变化时短暂高亮 + 显示增减；burnout 高位变红预警。
 */
export function StoryStatsHud({ stats, tension }: StoryStatsHudProps) {
  const prev = useRef<Stats>(stats);
  const [pulse, setPulse] = useState<Partial<Record<keyof Stats, number>>>({});

  useEffect(() => {
    const deltas: Partial<Record<keyof Stats, number>> = {};
    for (const { key } of ROWS) {
      const d = (stats[key] ?? 0) - (prev.current[key] ?? 0);
      if (d !== 0) deltas[key] = d;
    }
    prev.current = stats;
    if (Object.keys(deltas).length) {
      setPulse(deltas);
      const t = setTimeout(() => setPulse({}), 1500);
      return () => clearTimeout(t);
    }
  }, [stats]);

  const tensionPct = Math.max(0, Math.min(100, Math.round(tension ?? 0)));
  return (
    <div className="story-stats-hud">
      {tension != null ? (
        <div className="story-stats-hud__tension" title="故事张力">
          <span className="story-stats-hud__label">张力</span>
          <span className="story-tension-bar">
            <span
              className={`story-tension-bar__fill ${tensionPct >= 70 ? "is-high" : ""}`}
              style={{ width: `${tensionPct}%` }}
            />
          </span>
          <span className="story-stats-hud__value">{tensionPct}</span>
        </div>
      ) : null}
      {ROWS.map(({ key, label }) => {
        const val = stats[key] ?? 0;
        const delta = pulse[key];
        const warn = key === "burnout" && val >= 70;
        return (
          <div key={key} className={`story-stats-hud__item ${warn ? "is-warn" : ""}`}>
            <span className="story-stats-hud__label">{label}</span>
            <span className="story-stats-hud__value">{val}</span>
            {delta != null ? (
              <span className={`story-stats-hud__delta ${delta > 0 ? "up" : "down"}`}>
                {delta > 0 ? `+${delta}` : delta}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
