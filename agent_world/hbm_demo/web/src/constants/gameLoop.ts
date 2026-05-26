/** Game loop timing — PLAN2 §二 / dev_logs/31 Phase 2 F14. */

export const POLL_INTERVAL_MS = 800;
export const DELTA_POLL_MS = 300;
export const DELTA_POLL_PAUSED_MS = 1500;
/** Phase 5 — WebSocket push (production default). Dev uses HTTP poll to avoid Vite WS proxy EPIPE. */
function readWorldStreamEnabled(): boolean {
  const env = import.meta.env;
  if (!env) {
    return false;
  }
  const raw = env.VITE_WORLD_STREAM;
  if (raw === "true") {
    return true;
  }
  if (raw === "false") {
    return false;
  }
  return !env.DEV;
}

export const WORLD_STREAM_ENABLED = readWorldStreamEnabled();
export const WORLD_STREAM_FALLBACK_POLL_MS = 5000;
export const MAX_POLL_ATTEMPTS = 120;
export const MAX_TURNS = 25;

export const PLAYER_SENDER = "玩家";
