import { useEffect, useRef, useState } from "react";
import type { Stats } from "../api/types";

export interface StatusPanelProps {
  stats: Stats;
  phase: string;
  playerTurn: number;
  maxTurns?: number;
  placeLabel: string;
  presentAgents?: string[];
  onReset?: () => void;
  resetDisabled?: boolean;
}

const STAT_ROWS: { key: keyof Stats; label: string }[] = [
  { key: "vision", label: "Vision" },
  { key: "execution", label: "Execution" },
  { key: "trust", label: "Trust" },
  { key: "burnout", label: "Burnout" },
];

/** F2-2 + F4-5 — Stats 变化高亮动画；Turn x / 25。 */
export function StatusPanel({
  stats,
  phase,
  playerTurn,
  maxTurns = 25,
  placeLabel,
  presentAgents = [],
  onReset,
  resetDisabled = false,
}: StatusPanelProps) {
  const prevStatsRef = useRef(stats);
  const [pulseKeys, setPulseKeys] = useState<Set<keyof Stats>>(new Set());

  useEffect(() => {
    const changed = new Set<keyof Stats>();
    for (const { key } of STAT_ROWS) {
      if (prevStatsRef.current[key] !== stats[key]) {
        changed.add(key);
      }
    }
    if (changed.size > 0) {
      setPulseKeys(changed);
      const timer = setTimeout(() => setPulseKeys(new Set()), 700);
      prevStatsRef.current = stats;
      return () => clearTimeout(timer);
    }
    prevStatsRef.current = stats;
    return undefined;
  }, [stats]);

  return (
    <>
      <div className="panel__header">Status</div>
      <div className="status-panel__wrap">
        <div className="panel__body status-panel">
          <section className="status-panel__section">
          <h2 className="status-panel__title">核心数值</h2>
          <ul className="stat-list">
            {STAT_ROWS.map(({ key, label }) => (
              <li key={key} className="stat-list__item">
                <span className="stat-list__label">{label}</span>
                <span
                  className={[
                    "stat-list__value",
                    pulseKeys.has(key) ? "stat-list__value--pulse" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  {stats[key]}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="status-panel__section">
          <h2 className="status-panel__title">进度</h2>
          <dl className="meta-list">
            <div className="meta-list__row">
              <dt>Phase</dt>
              <dd>{phase}</dd>
            </div>
            <div className="meta-list__row">
              <dt>Turn</dt>
              <dd className="meta-list__turn">
                <span className="meta-list__turn-current">{playerTurn}</span>
                <span className="meta-list__turn-sep">/</span>
                <span className="meta-list__turn-max">{maxTurns}</span>
              </dd>
            </div>
          </dl>
        </section>

        <section className="status-panel__section">
          <h2 className="status-panel__title">当前地点</h2>
          <p className="status-panel__place">{placeLabel}</p>
          {presentAgents.length > 0 ? (
            <ul className="presence-list">
              {presentAgents.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : null}
        </section>
        </div>
        {onReset ? (
          <div className="status-panel__footer">
            <button
              type="button"
              className="status-panel__reset-btn"
              onClick={onReset}
              disabled={resetDisabled}
            >
              重开
            </button>
          </div>
        ) : null}
      </div>
    </>
  );
}
