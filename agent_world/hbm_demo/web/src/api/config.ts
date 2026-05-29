/** Demo API constants — aligned with backend `game_service.DEFAULT_SIM_ID`. */

export const SIM_ID = "hbm_memory_war";

/** Vite dev proxy serves `/api` on same origin; Node tests set `VITE_API_BASE`. */
function readNodeEnv(key: string): string | undefined {
  const proc = (globalThis as { process?: { env?: Record<string, string | undefined> } })
    .process;
  const value = proc?.env?.[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function readApiRoot(): string {
  const metaEnv =
    typeof import.meta !== "undefined"
      ? (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
      : undefined;
  const fromVite = metaEnv?.VITE_API_BASE;
  if (typeof fromVite === "string" && fromVite.length > 0) {
    return fromVite;
  }
  return readNodeEnv("VITE_API_BASE") ?? "";
}

export const API_ROOT = readApiRoot();

export const API_PREFIX = `${API_ROOT}/api/hbm/simulations/${SIM_ID}`;

/** PLAN2 §四 — ensures API 2 timeout path (start_tick + 8). */
export const DEFAULT_TICK_COUNT = 8;

/** §5.2 — single poll request timeout (ms). */
export const ACTION_RESULT_TIMEOUT_MS = 30_000;

/** §5.2 — health / session reads (ms). */
export const READ_TIMEOUT_MS = 30_000;

/** §5.2 — player-turn matches backend IPC default (600s). No abort when omitted. */
export const PLAYER_TURN_TIMEOUT_MS = 600_000;
