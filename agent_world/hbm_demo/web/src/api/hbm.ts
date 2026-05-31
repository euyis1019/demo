import { apiGet, apiPost } from "./client";
import {
  ACTION_RESULT_TIMEOUT_MS,
  apiPrefix,
  LOBBY_ROOT,
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

export { getSimId, setSimId, apiPrefix, DEFAULT_TICK_COUNT } from "./config";
export { HbmApiError, userMessageForStatus } from "./errors";
export type * from "./types";

/**
 * GET /health — does **not** throw on HTTP 503 (PLAN2 F1-5).
 * Check `success` and `data.ready` for Runner readiness.
 */
export async function getHealth(): Promise<ApiResponse<HealthData>> {
  return apiGet<HealthData>(`${apiPrefix()}/health`, undefined, {
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
    `${apiPrefix()}/session/start`,
    {},
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** POST /session/reset — reset Runner world + Flask session. */
export async function resetSession(): Promise<ApiResponse<SessionStartData>> {
  return apiPost<SessionStartData>(
    `${apiPrefix()}/session/reset`,
    {},
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** GET /session */
export async function getSession(): Promise<ApiResponse<SessionSnapshot>> {
  return apiGet<SessionSnapshot>(`${apiPrefix()}/session`, undefined, {
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
  return apiPost<PlayerTurnData>(`${apiPrefix()}/player-turn`, payload, {
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
  return apiPost<PlayerActionData>(`${apiPrefix()}/player-action`, request, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

export interface JoinableGroupsData {
  groups: { group_id: number }[];
  gate_enabled: boolean;
}

/** GET /joinable-groups — 玩家当前可加入的群（已 F2F 见过成员且其同意）。 */
export async function getJoinableGroups(): Promise<ApiResponse<JoinableGroupsData>> {
  return apiGet<JoinableGroupsData>(`${apiPrefix()}/joinable-groups`, undefined, {
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
  return apiGet<ActionResultData>(`${apiPrefix()}/action-result`, query, {
    timeoutMs: ACTION_RESULT_TIMEOUT_MS,
  });
}

/** GET /world-delta — F14 session-scoped incremental sync. */
export async function getWorldDelta(
  sinceTick: number,
): Promise<ApiResponse<WorldDeltaData>> {
  return apiGet<WorldDeltaData>(
    `${apiPrefix()}/world-delta`,
    { since_tick: String(sinceTick) },
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** GET /world-snapshot — F12 full-world calibration. */
export async function getWorldSnapshot(): Promise<ApiResponse<WorldSnapshot>> {
  return apiGet<WorldSnapshot>(`${apiPrefix()}/world-snapshot`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

/** GET /env-status — optional debug (PLAN2 F5-5). */
export async function getEnvStatus(): Promise<ApiResponse<EnvStatusData>> {
  return apiGet<EnvStatusData>(`${apiPrefix()}/env-status`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
    allowHttpStatuses: [503],
  });
}

/** GET /world-loop/status — F13 pause/resume state. */
export async function getWorldLoopStatus(): Promise<ApiResponse<WorldLoopStatusData>> {
  return apiGet<WorldLoopStatusData>(`${apiPrefix()}/world-loop/status`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
    allowHttpStatuses: [503],
  });
}

/** POST /world-loop/pause — F13 freeze world tick loop. */
export async function pauseWorldLoop(): Promise<ApiResponse<WorldLoopStatusData>> {
  return apiPost<WorldLoopStatusData>(
    `${apiPrefix()}/world-loop/pause`,
    {},
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** POST /world-loop/resume — F13 resume world tick loop. */
export async function resumeWorldLoop(): Promise<ApiResponse<WorldLoopStatusData>> {
  return apiPost<WorldLoopStatusData>(
    `${apiPrefix()}/world-loop/resume`,
    {},
    { timeoutMs: READ_TIMEOUT_MS },
  );
}

/** GET /prompt-trace/by-ref — F15 UI lookup. */
export async function getPromptTraceByRef(
  refKey: string,
): Promise<ApiResponse<PromptTraceData>> {
  return apiGet<PromptTraceData>(
    `${apiPrefix()}/prompt-trace/by-ref`,
    { ref_key: refKey },
    { timeoutMs: READ_TIMEOUT_MS, allowHttpStatuses: [404] },
  );
}

/** GET /prompt-trace/{id} — F15 full trace. */
export async function getPromptTrace(
  traceId: string,
): Promise<ApiResponse<PromptTraceData>> {
  return apiGet<PromptTraceData>(
    `${apiPrefix()}/prompt-trace/${encodeURIComponent(traceId)}`,
    undefined,
    { timeoutMs: READ_TIMEOUT_MS, allowHttpStatuses: [404] },
  );
}


// ============ 大厅：选已有故事 / 建新故事 / 激活起世界 ============

export interface StoryInfo {
  story_id: string;
  title: string;
  has_assets: boolean;
  agents: number;
}

export interface CreateStoryRequest {
  premise: string;
  player?: string;
  title?: string;
  acts?: number;
  with_assets?: boolean;
}

export interface JobStatus {
  status: "running" | "done" | "error";
  step: string;
  story_id: string | null;
  error: string | null;
  assets?: string;
}

/** GET 大厅故事列表 */
export async function listStories(): Promise<ApiResponse<{ stories: StoryInfo[] }>> {
  return apiGet<{ stories: StoryInfo[] }>(`${LOBBY_ROOT}/stories`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

/** POST 用一段剧情新建故事（后台异步设计+出图），返回 job_id */
export async function createStory(
  req: CreateStoryRequest,
): Promise<ApiResponse<{ job_id: string }>> {
  return apiPost<{ job_id: string }>(`${LOBBY_ROOT}/stories`, req, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

/** GET 生成任务进度 */
export async function getJob(jobId: string): Promise<ApiResponse<JobStatus>> {
  return apiGet<JobStatus>(`${LOBBY_ROOT}/jobs/${encodeURIComponent(jobId)}`, undefined, {
    timeoutMs: READ_TIMEOUT_MS,
  });
}

/** POST 激活某故事（确保 Runner 在跑、设为当前故事）；ready=true 才能开玩 */
export async function activateStory(
  storyId: string,
): Promise<ApiResponse<{ story_id: string; ready: boolean }>> {
  return apiPost<{ story_id: string; ready: boolean }>(
    `${LOBBY_ROOT}/activate`,
    { story_id: storyId },
    { timeoutMs: 120_000 },
  );
}
