import { useEffect, useState } from "react";
import { getEnvStatus } from "../../api/drama";

const ENV_POLL_MS = 400;

/** Poll Runner env-status.current_tick for world-delta sync cadence. */
export function useEnvStatus(enabled: boolean): number | null {
  const [currentTick, setCurrentTick] = useState<number | null>(null);

  useEffect(() => {
    if (!enabled) {
      setCurrentTick(null);
      return undefined;
    }

    let cancelled = false;

    async function refresh() {
      try {
        const response = await getEnvStatus();
        const tick = response.data?.current_tick;
        if (!cancelled && typeof tick === "number") {
          setCurrentTick(tick);
        }
      } catch {
        if (!cancelled) {
          setCurrentTick(null);
        }
      }
    }

    void refresh();
    const timer = setInterval(() => void refresh(), ENV_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled]);

  return currentTick;
}
