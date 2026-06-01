import { useEffect, useRef, useState } from "react";
import type { StatDimension, Stats } from "../../api/types";

export interface StoryStatsHudProps {
  stats: Stats;
  /** 属性维度定义（数据驱动：来自活跃 Story Pack 的 meta.stats）。 */
  dimensions?: StatDimension[];
}

/**
 * 剧情模式数值 HUD（体检 G6）：把后端已下发的 stats 接到剧情模式。
 * 维度集数据驱动（meta.stats）；数值变化时短暂高亮 + 显示增减。
 */
export function StoryStatsHud({ stats, dimensions = [] }: StoryStatsHudProps) {
  const prev = useRef<Stats>(stats);
  const [pulse, setPulse] = useState<Record<string, number>>({});

  useEffect(() => {
    const deltas: Record<string, number> = {};
    for (const key of Object.keys(stats)) {
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

  return (
    <div className="story-stats-hud">
      {/* 维度由活跃 Story Pack 的 meta.stats 决定；故事未定义属性面板就不显示。 */}
      {dimensions.map(({ key, label }) => {
        const val = stats[key] ?? 0;
        const delta = pulse[key];
        return (
          <div key={key} className="story-stats-hud__item">
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
