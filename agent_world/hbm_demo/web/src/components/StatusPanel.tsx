import type { Stats } from "../api/types";

export interface StatusPanelProps {
  stats: Stats;
  phase: string;
  playerTurn: number;
  maxTurns?: number;
  placeLabel: string;
  presentAgents?: string[];
}

const STAT_ROWS: { key: keyof Stats; label: string }[] = [
  { key: "vision", label: "Vision" },
  { key: "execution", label: "Execution" },
  { key: "trust", label: "Trust" },
  { key: "burnout", label: "Burnout" },
];

/** F2-2 — 四维 Stats、Phase、Turn、地点（dev_logs/03 左栏）。 */
export function StatusPanel({
  stats,
  phase,
  playerTurn,
  maxTurns = 25,
  placeLabel,
  presentAgents = [],
}: StatusPanelProps) {
  return (
    <>
      <div className="panel__header">Status</div>
      <div className="panel__body status-panel">
        <section className="status-panel__section">
          <h2 className="status-panel__title">核心数值</h2>
          <ul className="stat-list">
            {STAT_ROWS.map(({ key, label }) => (
              <li key={key} className="stat-list__item">
                <span className="stat-list__label">{label}</span>
                <span className="stat-list__value">{stats[key]}</span>
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
              <dd>
                {playerTurn} / {maxTurns}
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
    </>
  );
}
