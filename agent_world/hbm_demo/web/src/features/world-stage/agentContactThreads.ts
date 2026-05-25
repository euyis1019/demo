import type { GameMessage, StateChange } from "../../api/types";
import { agentDisplayName } from "../../constants/agents";
import { groupDisplayLabel } from "../../constants/groups";
import type { AgentInbox } from "../../store/worldSync";
import { threadKeyGrp, threadKeyRdc } from "../../store/worldSync";

export type ContactThreadKind = "rdc" | "grp" | "os";

export interface ContactThread {
  key: string;
  kind: ContactThreadKind;
  title: string;
  preview: string;
  sortTick: number;
  archived: boolean;
  messages: GameMessage[];
  osEntries: StateChange[];
}

function peerLabelFromRdcKey(key: string, nameMap: Record<string, string>): string {
  const peer = key.slice("rdc:".length);
  if (peer === "unknown") {
    return "未知联系人";
  }
  return agentDisplayName(peer, nameMap);
}

function previewFromMessages(messages: GameMessage[]): string {
  const last = messages.at(-1);
  if (!last) {
    return "";
  }
  if (last.is_system) {
    return last.content;
  }
  const text = last.content.trim();
  return text.length > 36 ? `${text.slice(0, 36)}…` : text;
}

/** WeChat-style unified contact list for one agent's inbox. */
export function buildContactThreads(
  inbox: AgentInbox,
  nameMap: Record<string, string>,
  ownerAgentId: string,
): ContactThread[] {
  const threads: ContactThread[] = [];
  const rdcBuckets = new Map<string, GameMessage[]>();

  for (const message of inbox.rdc) {
    const key = threadKeyRdc(message, ownerAgentId);
    const bucket = rdcBuckets.get(key);
    if (bucket) {
      bucket.push(message);
    } else {
      rdcBuckets.set(key, [message]);
    }
  }

  for (const [key, messages] of rdcBuckets) {
    const lastTick = messages.at(-1)?.attempted_at ?? 0;
    threads.push({
      key,
      kind: "rdc",
      title: peerLabelFromRdcKey(key, nameMap),
      preview: previewFromMessages(messages),
      sortTick: lastTick,
      archived: inbox.archivedThreadKeys.includes(key),
      messages,
      osEntries: [],
    });
  }

  const grpBuckets = new Map<string, GameMessage[]>();
  for (const message of inbox.grp) {
    const key = threadKeyGrp(message);
    const bucket = grpBuckets.get(key);
    if (bucket) {
      bucket.push(message);
    } else {
      grpBuckets.set(key, [message]);
    }
  }

  for (const [key, messages] of grpBuckets) {
    const groupId = Number(key.slice("grp:".length));
    const lastTick = messages.at(-1)?.attempted_at ?? 0;
    threads.push({
      key,
      kind: "grp",
      title: groupDisplayLabel(Number.isNaN(groupId) ? undefined : groupId) ?? key,
      preview: previewFromMessages(messages),
      sortTick: lastTick,
      archived: inbox.archivedThreadKeys.includes(key),
      messages,
      osEntries: [],
    });
  }

  if (inbox.osLog.length > 0) {
    const last = inbox.osLog.at(-1);
    threads.push({
      key: "os:self",
      kind: "os",
      title: "内心 OS",
      preview: last ? previewFromMessages([{ sender: "", content: last.content, type: "RDC" }]) : "",
      sortTick: last?.at_tick ?? 0,
      archived: false,
      messages: [],
      osEntries: inbox.osLog,
    });
  }

  return threads.sort((a, b) => b.sortTick - a.sortTick);
}
