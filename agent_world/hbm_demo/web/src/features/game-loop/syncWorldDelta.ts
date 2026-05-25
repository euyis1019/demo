import type { Dispatch } from "react";
import { getEnvStatus, getWorldDelta } from "../../api/hbm";
import { DELTA_POLL_MS } from "../../constants/gameLoop";
import type { GameAction } from "../../store/gameStore";
import { applyWorldDeltaPayload } from "./worldDeltaApply";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** Pull one incremental delta window. */
export async function pullWorldDelta(
  dispatch: Dispatch<GameAction>,
  sinceTick: number,
): Promise<number> {
  const response = await getWorldDelta(sinceTick);
  if (!response.data) {
    return sinceTick;
  }
  return applyWorldDeltaPayload(dispatch, response.data, sinceTick);
}

/**
 * Catch up after player-turn enqueue — poll until loop pauses/stops or activity seen.
 * Prevents missing early ticks while the UI was still initializing.
 */
export async function syncWorldDeltaCatchUp(
  dispatch: Dispatch<GameAction>,
  sinceTick: number,
  options?: { maxAttempts?: number; intervalMs?: number },
): Promise<number> {
  const maxAttempts = options?.maxAttempts ?? 80;
  const intervalMs = options?.intervalMs ?? DELTA_POLL_MS;
  let cursor = sinceTick;
  let sawActivity = false;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (attempt > 0) {
      await sleep(intervalMs);
    }

    const before = cursor;
    cursor = await pullWorldDelta(dispatch, cursor);
    if (cursor > before) {
      sawActivity = true;
    }

    try {
      const envResp = await getEnvStatus();
      const loopState = envResp.data?.loop_state;
      if (loopState === "paused" || loopState === "stopped") {
        cursor = await pullWorldDelta(dispatch, cursor);
        break;
      }
      if (sawActivity && loopState === "running") {
        // Keep polling briefly while batch still running.
        continue;
      }
    } catch {
      break;
    }
  }

  return cursor;
}
