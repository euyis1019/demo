import type { ReactNode } from "react";

export interface ThreeColumnLayoutProps {
  status: ReactNode;
  main: ReactNode;
  observer: ReactNode;
}

/** F2-1 — 左 240px / 中 flex / 右 320px（PLAN2 / dev_logs/03）。 */
export function ThreeColumnLayout({
  status,
  main,
  observer,
}: ThreeColumnLayoutProps) {
  return (
    <div className="app-shell" data-phase="F2">
      <aside className="panel panel--status" aria-label="状态面板">
        {status}
      </aside>
      <section className="panel panel--main" aria-label="主交互区">
        {main}
      </section>
      <aside className="panel panel--observer" aria-label="上帝视角">
        {observer}
      </aside>
    </div>
  );
}
