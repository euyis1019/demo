/** HBM demo API constants。SIM_ID 运行期可变：大厅里选/建故事并激活后 setSimId 切换。 */

let _simId = "canglan_sword";

export function getSimId(): string {
  return _simId;
}

export function setSimId(simId: string): void {
  if (simId) _simId = simId;
}

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

/** 当前故事的 API 前缀（运行期按 setSimId 变化，故用函数而非常量）。 */
export function apiPrefix(): string {
  return `${API_ROOT}/api/drama/simulations/${encodeURIComponent(_simId)}`;
}

/** 大厅（选/建/激活故事）API 根。 */
export const LOBBY_ROOT = `${API_ROOT}/api/drama/lobby`;

/** PLAN2 §四 — ensures API 2 timeout path (start_tick + 8). */
export const DEFAULT_TICK_COUNT = 8;

/** §5.2 — single poll request timeout (ms). */
export const ACTION_RESULT_TIMEOUT_MS = 30_000;

/** §5.2 — health / session reads (ms). */
export const READ_TIMEOUT_MS = 30_000;

/** §5.2 — player-turn matches backend IPC default (600s). No abort when omitted. */
export const PLAYER_TURN_TIMEOUT_MS = 600_000;
