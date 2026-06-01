import { DRAMA_DEMO_FLASK_ORIGIN } from "../constants/ports";
import { API_ROOT } from "./config";
import { errorCodeForStatus, DramaApiError, userMessageForStatus } from "./errors";
import type { ApiResponse } from "./types";

export interface RequestOptions {
  /** Abort after N ms; omit for no timeout (player-turn). */
  timeoutMs?: number;
  signal?: AbortSignal;
}

function resolveOrigin(): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  if (API_ROOT) {
    return API_ROOT;
  }
  return DRAMA_DEMO_FLASK_ORIGIN;
}

function buildUrl(path: string, query?: Record<string, string | undefined>): string {
  const url = new URL(path, resolveOrigin());
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }
  return url.toString();
}

async function parseJsonResponse<T>(
  response: Response,
): Promise<ApiResponse<T>> {
  let body: ApiResponse<T>;
  try {
    body = (await response.json()) as ApiResponse<T>;
  } catch {
    throw new DramaApiError(
      userMessageForStatus(response.status, "响应不是有效 JSON"),
      response.status,
      errorCodeForStatus(response.status),
    );
  }
  return body;
}

async function request<T>(
  path: string,
  init: RequestInit,
  options?: RequestOptions,
): Promise<{ response: Response; body: ApiResponse<T> }> {
  const controller = new AbortController();
  const timeoutMs = options?.timeoutMs;
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  if (options?.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener("abort", () => controller.abort(), {
        once: true,
      });
    }
  }

  if (timeoutMs !== undefined && timeoutMs > 0) {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      credentials: "include",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init.headers ?? {}),
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new DramaApiError(
        timeoutMs ? "请求超时" : "请求已取消",
        0,
        timeoutMs ? "IPC_TIMEOUT" : "NETWORK_ERROR",
      );
    }
    throw new DramaApiError(
      err instanceof Error ? err.message : "网络错误",
      0,
      "NETWORK_ERROR",
    );
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
    }
  }

  const body = await parseJsonResponse<T>(response);
  return { response, body };
}

/** GET — throws on `success: false` unless `allowErrorStatus` is set. */
export async function apiGet<T>(
  path: string,
  query?: Record<string, string | undefined>,
  options?: RequestOptions & { allowHttpStatuses?: number[] },
): Promise<ApiResponse<T>> {
  const url = buildUrl(path, query);
  const { response, body } = await request<T>(url, { method: "GET" }, options);

  const allowed = options?.allowHttpStatuses ?? [];
  if (!response.ok && !allowed.includes(response.status)) {
    throw new DramaApiError(
      body.error ?? userMessageForStatus(response.status),
      response.status,
      errorCodeForStatus(response.status),
      body,
    );
  }
  if (!body.success && !allowed.includes(response.status)) {
    throw new DramaApiError(
      body.error ?? userMessageForStatus(response.status),
      response.status,
      errorCodeForStatus(response.status),
      body,
    );
  }
  return body;
}

/** POST JSON — throws on failure. */
export async function apiPost<T>(
  path: string,
  payload: unknown,
  options?: RequestOptions,
): Promise<ApiResponse<T>> {
  const url = buildUrl(path);
  const { response, body } = await request<T>(
    url,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    options,
  );

  if (!response.ok) {
    throw new DramaApiError(
      body.error ?? userMessageForStatus(response.status),
      response.status,
      errorCodeForStatus(response.status),
      body,
    );
  }
  if (!body.success) {
    throw new DramaApiError(
      body.error ?? "API 返回 success: false",
      response.status,
      "API_ERROR",
      body,
    );
  }
  return body;
}
