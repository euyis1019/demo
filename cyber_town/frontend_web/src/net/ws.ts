import { SEND_THROTTLE } from "../config";
import type { CommandAction, HelloAck, SnapshotFrame } from "./protocol";
import { useWorld } from "../store/worldStore";
import { useChat } from "../store/chatStore";

// WS 单例：连后端 /ws/world，收 hello/snapshot 写 store，发玩家命令（含节流+重连）。
// 复刻 Godot world_net.gd 的契约：上行 {action, client_seq, kwargs}，命令白名单 5 个。

type TimelineCb = (agentId: number, data: any) => void;

class WorldNet {
  private sock: WebSocket | null = null;
  private clientSeq = 0;
  private lastSend: Record<string, number> = {};
  private retry = 1.0;
  private timelineCbs = new Set<TimelineCb>();
  private started = false;

  start() {
    if (this.started) return;
    this.started = true;
    this.connect();
  }

  private wsUrl(): string {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}/ws/world`;
  }

  private connect() {
    try {
      this.sock = new WebSocket(this.wsUrl());
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.sock.onopen = () => {
      this.retry = 1.0;
      useWorld.getState().setConnected(true);
    };
    this.sock.onclose = () => {
      useWorld.getState().setConnected(false);
      this.scheduleReconnect();
    };
    this.sock.onerror = () => this.sock?.close();
    this.sock.onmessage = (ev) => this.onMessage(ev.data);
  }

  private scheduleReconnect() {
    const delay = this.retry;
    this.retry = Math.min(this.retry * 2, 10);
    setTimeout(() => this.connect(), delay * 1000);
  }

  private onMessage(raw: string) {
    let frame: any;
    try {
      frame = JSON.parse(raw);
    } catch {
      return;
    }
    const w = useWorld.getState();
    switch (frame.type) {
      case "hello_ack":
        w.applyHello(frame.data as HelloAck);
        break;
      case "snapshot": {
        const f = frame as SnapshotFrame;
        w.applySnapshot(f.t, f.data);
        // 累积聊天日志（名册来自 hello）
        const names: Record<number, string> = {};
        const roster = w.hello?.agents ?? {};
        for (const [k, v] of Object.entries(roster)) names[Number(k)] = v;
        useChat.getState().ingest(f.data.player_view ?? {}, names, w.playerId);
        break;
      }
      case "ack":
      case "error":
      default:
        break;
    }
  }

  // 发命令；被节流/未连接返回 false
  send(action: CommandAction, kwargs: Record<string, unknown>): boolean {
    if (!this.sock || this.sock.readyState !== WebSocket.OPEN) return false;
    const now = performance.now() / 1000;
    if (now - (this.lastSend[action] ?? -10) < SEND_THROTTLE) return false;
    this.lastSend[action] = now;
    this.clientSeq += 1;
    this.sock.send(JSON.stringify({ action, client_seq: this.clientSeq, kwargs }));
    return true;
  }

  requestMove(placeId: string) {
    return this.send("request_move", { place_id: placeId });
  }
  speakToLocal(content: string) {
    return this.send("speak_to_local", { content });
  }
  sendMessage(target: number, content: string) {
    return this.send("send_message", { target, content });
  }
  sendToGroup(groupId: number, content: string) {
    return this.send("send_to_group", { group_id: groupId, content });
  }

  onTimeline(cb: TimelineCb) {
    this.timelineCbs.add(cb);
    return () => this.timelineCbs.delete(cb);
  }
  async fetchTimeline(agentId: number) {
    try {
      const r = await fetch(`/agents/${agentId}/timeline?limit=60`);
      if (!r.ok) return;
      const data = await r.json();
      this.timelineCbs.forEach((cb) => cb(agentId, data));
    } catch {
      /* ignore */
    }
  }
}

export const net = new WorldNet();
