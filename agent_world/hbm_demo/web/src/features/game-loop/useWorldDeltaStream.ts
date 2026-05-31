import { useEffect, useRef } from "react";
import type { WorldDeltaData } from "../../api/types";
import { apiPrefix } from "../../api/hbm";
import { WORLD_STREAM_FALLBACK_POLL_MS } from "../../constants/gameLoop";
import { useGameStoreContext } from "../../store";
import { applyWorldDeltaPayload } from "./worldDeltaApply";

function worldStreamUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${apiPrefix()}/world-stream`;
}

/** F16 — WebSocket push for session delta (dev_logs/31 Phase 5 §14.4). */
export function useWorldDeltaStream(
  enabled: boolean,
  _paused: boolean,
  onConnected: (connected: boolean) => void,
): void {
  const { state, dispatch } = useGameStoreContext();
  const sinceTickRef = useRef(state.deltaSinceTick);
  const onConnectedRef = useRef(onConnected);

  useEffect(() => {
    sinceTickRef.current = state.deltaSinceTick;
  }, [state.deltaSinceTick]);

  useEffect(() => {
    onConnectedRef.current = onConnected;
  }, [onConnected]);

  useEffect(() => {
    if (!enabled) {
      onConnectedRef.current(false);
      return;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let reconnectDelayMs = WORLD_STREAM_FALLBACK_POLL_MS;

    const connect = () => {
      if (cancelled) {
        return;
      }
      if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
        return;
      }

      ws = new WebSocket(worldStreamUrl());

      ws.onopen = () => {
        if (cancelled || !ws) {
          return;
        }
        reconnectDelayMs = WORLD_STREAM_FALLBACK_POLL_MS;
        onConnectedRef.current(true);
        ws.send(JSON.stringify({ since_tick: sinceTickRef.current }));
      };

      ws.onmessage = (event) => {
        if (cancelled) {
          return;
        }
        try {
          const payload = JSON.parse(String(event.data)) as {
            success?: boolean;
            data?: WorldDeltaData;
            error?: string;
          };
          if (!payload.success || !payload.data) {
            return;
          }
          sinceTickRef.current = applyWorldDeltaPayload(
            dispatch,
            payload.data,
            sinceTickRef.current,
          );
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onerror = () => {
        onConnectedRef.current(false);
      };

      ws.onclose = () => {
        onConnectedRef.current(false);
        ws = null;
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, reconnectDelayMs);
          reconnectDelayMs = Math.min(Math.round(reconnectDelayMs * 1.5), 30_000);
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      onConnectedRef.current(false);
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, "component unmount");
      }
      ws = null;
    };
  }, [dispatch, enabled, _paused]);
}
