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
  WorldLoopStatusData,
  WorldDeltaData,
  WorldSnapshot,
  PromptTraceData,
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

/** POST /session/reset — reset Runner world + Flask session. */
export async function resetSession(): Promise<ApiResponse<SessionStartData>> {
  return apiPost<SessionStartData>(
    `${API_PREFIX}/session/reset`,
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

/** 玩家主动动作请求（私信/移动/加群）。 */
export interface PlayerActionRequest {
  action: "rdc" | "move" | "grp";
  target_id?: number;
  place_id?: string;
  group_id?: number;
  content?: string;
}

export interface PlayerActionData {
  accepted: boolean;
  reason?: string;
  hint?: string;
  [key: string]: unknown;
}

/** POST /player-action — 玩家私信(rdc)/移动(move)/加群(grp)。加群受门控。 */
export async function postPlayerAction(
  request: PlayerActionRequest,
): Promise<ApiResponse<PlayerActionData>> {
  return apiPost<PlayerActionData>(`${API_PREFIX}/player-action`, request, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

/** GET /action-result — optional since_tick for F11 incremental delta. */
export async function getActionResult(
  taskId: string,
  options?: { place_id?: string; since_tick?: number },
): Promise<ApiResponse<ActionResultData>> {
  const query: Record<string, string | undefined> = {
    task_id: taskId,
    place_id: options?.place_id,
  };
  if (options?.since_tick !== undefined) {
    query.since_tick = String(options.since_tick);
  }
  return apiGet<ActionResultData>(`${API_PREFIX}/action-result`, query, {
    timeoutMs: ACTION_RESULT_TIMEOUT_MS,
  });
}

/** GET /world-delta — F14 session-scoped incremental sync. */
export async function getWorldDelta(
  sinceTick: number,
): Promise<ApiResponse<WorldDeltaData>> {
  return apiGet<WorldDeltaData>(
    `${API_PREFIX}/world-delta`,
    { since_tick: String(sinceTick) },
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** GET /world-snapshot — F12 full-world calibration. */
export async function getWorldSnapshot(): Promise<ApiResponse<WorldSnapshot>> {
  return apiGet<WorldSnapshot>(`${API_PREFIX}/world-snapshot`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

/** GET /env-status — optional debug (PLAN2 F5-5). */
export async function getEnvStatus(): Promise<ApiResponse<EnvStatusData>> {
  return apiGet<EnvStatusData>(`${API_PREFIX}/env-status`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
    allowHttpStatuses: [503],
  });
}

/** GET /world-loop/status — F13 pause/resume state. */
export async function getWorldLoopStatus(): Promise<ApiResponse<WorldLoopStatusData>> {
  return apiGet<WorldLoopStatusData>(`${API_PREFIX}/world-loop/status`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
    allowHttpStatuses: [503],
  });
}

/** POST /world-loop/pause — F13 freeze world tick loop. */
export async function pauseWorldLoop(): Promise<ApiResponse<WorldLoopStatusData>> {
  return apiPost<WorldLoopStatusData>(
    `${API_PREFIX}/world-loop/pause`,
    {},
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** POST /world-loop/resume — F13 resume world tick loop. */
export async function resumeWorldLoop(): Promise<ApiResponse<WorldLoopStatusData>> {
  return apiPost<WorldLoopStatusData>(
    `${API_PREFIX}/world-loop/resume`,
    {},
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** GET /prompt-trace/by-ref — F15 UI lookup. */
export async function getPromptTraceByRef(
  refKey: string,
): Promise<ApiResponse<PromptTraceData>> {
  return apiGet<PromptTraceData>(
    `${API_PREFIX}/prompt-trace/by-ref`,
    { ref_key: refKey },
    { timeoutMs: READ_TIMEOUT_MS, allowHttpStatuses: [404] },
  );
}

/** GET /prompt-trace/{id} — F15 full trace. */
export async function getPromptTrace(
  traceId: string,
): Promise<ApiResponse<PromptTraceData>> {
  return apiGet<PromptTraceData>(
    `${API_PREFIX}/prompt-trace/${encodeURIComponent(traceId)}`,
    undefined,
    { timeoutMs: READ_TIMEOUT_MS, allowHttpStatuses: [404] },
  );
}
