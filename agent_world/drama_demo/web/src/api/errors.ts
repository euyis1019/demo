import type { ApiResponse } from "./types";

export type DramaErrorCode =
  | "RUNNER_NOT_READY"
  | "IPC_FAILED"
  | "IPC_TIMEOUT"
  | "HTTP_ERROR"
  | "API_ERROR"
  | "NETWORK_ERROR";

/** Thrown when an API call fails (except `getHealth` 503 — see `hbm.ts`). */
export class DramaApiError extends Error {
  readonly status: number;
  readonly code: DramaErrorCode;
  readonly body?: ApiResponse<unknown>;

  constructor(
    message: string,
    status: number,
    code: DramaErrorCode,
    body?: ApiResponse<unknown>,
  ) {
    super(message);
    this.name = "DramaApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

/** Map HTTP status to user-facing hint (PLAN2 F1-4). */
export function userMessageForStatus(status: number, fallback?: string): string {
  switch (status) {
    case 503:
      return "Runner 未就绪或数据库不可读，请先启动 run_drama";
    case 504:
      return "本回合处理超时（IPC），请稍后重试";
    case 502:
      return "仿真进程异常（IPC 失败）";
    case 404:
      return fallback ?? "请求的资源不存在";
    default:
      return fallback ?? `请求失败（HTTP ${status}）`;
  }
}

export function errorCodeForStatus(status: number): DramaErrorCode {
  switch (status) {
    case 503:
      return "RUNNER_NOT_READY";
    case 504:
      return "IPC_TIMEOUT";
    case 502:
      return "IPC_FAILED";
    default:
      return "HTTP_ERROR";
  }
}

export function throwApiError(
  status: number,
  body: ApiResponse<unknown> | undefined,
): never {
  const message = body?.error ?? userMessageForStatus(status);
  throw new DramaApiError(message, status, errorCodeForStatus(status), body);
}
