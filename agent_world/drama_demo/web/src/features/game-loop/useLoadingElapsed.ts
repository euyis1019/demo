import { useEffect, useState } from "react";

/** F5-1 — 加载期间每秒递增，停止时归零。 */
export function useLoadingElapsed(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return undefined;
    }

    setElapsed(0);
    const timer = setInterval(() => {
      setElapsed((value) => value + 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [active]);

  return elapsed;
}
