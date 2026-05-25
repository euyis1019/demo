import { useState } from "react";
import { WORLD_STREAM_ENABLED } from "../../constants/gameLoop";
import { useWorldDeltaPoll } from "./useWorldDeltaPoll";
import { useWorldDeltaStream } from "./useWorldDeltaStream";

/**
 * F14 + F16 — WebSocket primary, HTTP poll fallback (dev_logs/31 Phase 5).
 */
export function useWorldDeltaSync(enabled: boolean, paused: boolean): void {
  const [wsConnected, setWsConnected] = useState(false);
  const useStream = enabled && WORLD_STREAM_ENABLED;
  useWorldDeltaStream(useStream, paused, setWsConnected);
  useWorldDeltaPoll(enabled && (!useStream || !wsConnected), paused);
}
