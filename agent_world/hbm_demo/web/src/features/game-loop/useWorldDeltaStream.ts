import { useEffect, useRef } from "react";
import type { WorldDeltaData } from "../../api/types";
import { API_PREFIX, SIM_ID } from "../../api/hbm";
import { WORLD_STREAM_FALLBACK_POLL_MS } from "../../constants/gameLoop";
import { useGameStoreContext } from "../../store/GameStoreProvider";
import { applyWorldDeltaPayload } from "./worldDeltaApply";

function worldStreamUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${API_PREFIX}/simulations/${SIM_ID}/world-stream`;
}

/** F16 — WebSocket push for session delta (dev_logs/31 Phase 5 §14.4). */
export function useWorldDeltaStream(
  enabled: boolean,
  _paused: boolean,
  onConnected: (connected: boolean) => void,
): void {
  const { state, dispatch } = useGameStoreContext();
  const sinceTickRef = useRef(state.worldTick);
  const onConnectedRef = useRef(onConnected);

  useEffect(() => {
    sinceTickRef.current = state.worldTick;
  }, [state.worldTick]);

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

    const connect = () => {
      if (cancelled) {
        return;
      }
      ws = new WebSocket(worldStreamUrl());

      ws.onopen = () => {
        if (cancelled || !ws) {
          return;
        }
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
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, WORLD_STREAM_FALLBACK_POLL_MS);
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
      ws?.close();
    };
  }, [dispatch, enabled, _paused]);
}
