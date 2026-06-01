import type { ReactNode } from "react";

export interface TwoColumnLayoutProps {
  status: ReactNode;
  main: ReactNode;
}

/** F12 — 左 240px Status + 右 WorldStage（dev_logs/32 §6.1）。 */
export function TwoColumnLayout({ status, main }: TwoColumnLayoutProps) {
  return (
    <div className="app-shell app-shell--two-col" data-phase="F12">
      <aside className="panel panel--status" aria-label="状态面板">
        {status}
      </aside>
      <section className="panel panel--world" aria-label="世界舞台">
        {main}
      </section>
    </div>
  );
}
