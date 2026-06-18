import { SEND_THROTTLE, affinityTier, affinityLevel } from "../config";
import type { CommandAction, HelloAck, SnapshotFrame } from "./protocol";
import { useWorld } from "../store/worldStore";
import { useChat } from "../store/chatStore";
import { useToast } from "../ui/toastStore";

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
        const prevAgents = useWorld.getState().agents; // 升温检测要在覆盖前取旧值
        const prevBonds = useWorld.getState().bonds;
        w.applySnapshot(f.t, f.data);
        this.detectWarmth(prevAgents, useWorld.getState().agents, w.hello?.agents);
        this.detectBonds(prevBonds, f.data.bonds ?? {}, w.playerId, w.hello?.agents);
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
    // 送礼/帮忙/陪伴按「动作+对象」分别节流——给不同街坊连送不应互相挤掉
    const key = (action === "give_gift" || action === "lend_a_hand" || action === "spend_time")
      ? `${action}:${kwargs.target}` : action;
    if (now - (this.lastSend[key] ?? -10) < SEND_THROTTLE) return false;
    this.lastSend[key] = now;
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
  giveGift(target: number, item: string) {
    return this.send("give_gift", { target, item });
  }
  lendHand(target: number, item: string) {
    return this.send("lend_a_hand", { target, item });
  }
  spendTime(target: number, item: string) {
    return this.send("spend_time", { target, item });
  }

  // NPC 对玩家好感跨档升温 → 里程碑 toast（焐心小镇支柱1）
  private detectWarmth(
    prev: Record<string, any>, next: Record<string, any>,
    roster?: Record<string, string>,
  ) {
    for (const id of Object.keys(next)) {
      const np = next[id]?.affinity_to_player;
      const op = prev[id]?.affinity_to_player;
      if (typeof np === "number" && typeof op === "number" && affinityTier(np) > affinityTier(op)) {
        const name = roster?.[id] ?? id;
        useToast.getState().push(`${name} 把你当${affinityLevel(np)}了`, "milestone");
      }
    }
  }

  // NPC 对玩家新结「好友」/新生「心结」→ 里程碑 toast（B4）
  private detectBonds(
    prev: Record<string, Record<string, string>>,
    next: Record<string, Record<string, string>>,
    playerId: number, roster?: Record<string, string>,
  ) {
    const pid = String(playerId);
    for (const src of Object.keys(next)) {
      if (src === pid) continue;
      const nb = next[src]?.[pid];
      const ob = prev[src]?.[pid];
      if (nb && nb !== ob) {
        const name = roster?.[src] ?? src;
        useToast.getState().push(
          nb === "好友" ? `${name} 认你做好友了` : `${name} 和你生了心结…`, "milestone");
      }
    }
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
