import { apiGet, apiPost } from "./client";
import {
  ACTION_RESULT_TIMEOUT_MS,
  API_PREFIX,
  DEFAULT_TICK_COUNT,
  PLAYER_TURN_TIMEOUT_MS,
  READ_TIMEOUT_MS,
} from "./config";
import type {
  ActionResultData,
  ApiResponse,
  EnvStatusData,
  HealthData,
  PlayerTurnData,
  PlayerTurnRequest,
  SessionSnapshot,
  SessionStartData,
} from "./types";

export { SIM_ID, API_PREFIX, DEFAULT_TICK_COUNT } from "./config";
export { HbmApiError, userMessageForStatus } from "./errors";
export type * from "./types";

/**
 * GET /health — does **not** throw on HTTP 503 (PLAN2 F1-5).
 * Check `success` and `data.ready` for Runner readiness.
 */
export async function getHealth(): Promise<ApiResponse<HealthData>> {
  return apiGet<HealthData>(`${API_PREFIX}/health`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
    allowHttpStatuses: [503],
  });
}

export function isRunnerReady(health: ApiResponse<HealthData>): boolean {
  return health.success === true && health.data?.ready === true;
}

/** POST /session/start */
export async function startSession(): Promise<ApiResponse<SessionStartData>> {
  return apiPost<SessionStartData>(
    `${API_PREFIX}/session/start`,
    {},
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** GET /session */
export async function getSession(): Promise<ApiResponse<SessionSnapshot>> {
  return apiGet<SessionSnapshot>(`${API_PREFIX}/session`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

/** POST /player-turn — long timeout, default tick_count=8 (PLAN2 §四). */
export async function postPlayerTurn(
  request: PlayerTurnRequest,
): Promise<ApiResponse<PlayerTurnData>> {
  const payload = {
    ...request,
    tick_count: request.tick_count ?? DEFAULT_TICK_COUNT,
  };
  return apiPost<PlayerTurnData>(`${API_PREFIX}/player-turn`, payload, {
    timeoutMs: PLAYER_TURN_TIMEOUT_MS,
  });
}

/** GET /action-result */
export async function getActionResult(
  taskId: string,
  options?: { place_id?: string },
): Promise<ApiResponse<ActionResultData>> {
  return apiGet<ActionResultData>(
    `${API_PREFIX}/action-result`,
    { task_id: taskId, place_id: options?.place_id },
    { timeoutMs: ACTION_RESULT_TIMEOUT_MS },
  );
}

/** GET /env-status — optional debug (PLAN2 F5-5). */
export async function getEnvStatus(): Promise<ApiResponse<EnvStatusData>> {
  return apiGet<EnvStatusData>(`${API_PREFIX}/env-status`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
    allowHttpStatuses: [503],
  });
}
