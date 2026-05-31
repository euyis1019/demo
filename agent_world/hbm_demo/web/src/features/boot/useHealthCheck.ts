import { useCallback, useEffect } from "react";
import { getHealth, getSession, isRunnerReady } from "../../api/hbm";
import { HbmApiError } from "../../api/errors";
import { hydrateWorldFromServer } from "../game-loop/hydrateWorldSnapshot";
import { useGameStoreContext } from "../../store";

/** F3-1 — mount health check; 503 → BootScreen + manual retry. */
export function useHealthCheck() {
  const {
    state,
    setHealthChecking,
    setHealthResult,
    applySessionSnapshot,
    dispatch,
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
          await hydrateWorldFromServer(dispatch);
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
  }, [applySessionSnapshot, dispatch, setHealthChecking, setHealthResult]);

  useEffect(() => {
    // 选择界面尚未选/激活故事，别对默认 sim 预热 health/session/world；
    // 用户选定后 view 切到 boot，本 effect 随之触发，对正确的 sim 跑一次健康检查。
    if (state.view === "select") return;
    void checkHealth();
  }, [checkHealth, state.view]);

  return { retryHealth: checkHealth };
}
