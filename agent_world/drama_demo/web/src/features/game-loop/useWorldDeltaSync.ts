import { WORLD_STREAM_ENABLED } from "../../constants/gameLoop";
import { useWorldDeltaPoll } from "./useWorldDeltaPoll";
import { useWorldDeltaStream } from "./useWorldDeltaStream";

/**
 * F14 + F16 — HTTP poll always on; WebSocket adds push when available (dev_logs/31 Phase 5).
 *
 * Do not disable poll when WS connects: a half-open or session-less WS would block all sync.
 */
export function useWorldDeltaSync(
  enabled: boolean,
  paused: boolean,
  envTick: number | null = null,
): void {
  const useStream = enabled && WORLD_STREAM_ENABLED;
  useWorldDeltaPoll(enabled, paused, envTick);
  useWorldDeltaStream(useStream, paused, () => {});
}
