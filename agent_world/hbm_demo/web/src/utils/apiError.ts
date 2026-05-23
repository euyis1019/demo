import { HbmApiError } from "../api/errors";

export function errorMessage(err: unknown, fallback = "请求失败"): string {
  if (err instanceof HbmApiError) {
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return fallback;
}

export function isRunnerNotReadyError(err: unknown): boolean {
  return err instanceof HbmApiError && err.code === "RUNNER_NOT_READY";
}
