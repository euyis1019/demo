import { useCallback, useEffect } from "react";
import { getHealth, getSession, isRunnerReady } from "../api/hbm";
import { HbmApiError } from "../api/errors";
import { useGameStoreContext } from "../store/GameStoreProvider";

/** F3-1 — mount health check; 503 → BootScreen + manual retry. */
export function useHealthCheck() {
  const {
    setHealthChecking,
    setHealthResult,
    applySessionSnapshot,
  } = useGameStoreContext();

  const checkHealth = useCallback(async () => {
    setHealthChecking();
    try {
      const health = await getHealth();
      const ready = isRunnerReady(health);
      setHealthResult(ready, ready ? undefined : health.error);

      if (ready) {
        const session = await getSession();
        if (session.data?.initialized) {
          applySessionSnapshot(session.data);
        }
      }
    } catch (err) {
      const message =
        err instanceof HbmApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "健康检查失败";
      setHealthResult(false, message);
    }
  }, [applySessionSnapshot, setHealthChecking, setHealthResult]);

  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  return { retryHealth: checkHealth };
}
