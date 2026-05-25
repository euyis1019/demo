/**
 * F12 Phase 3 — worldSync merge unit tests (dev_logs/32 §6.5–6.6).
 * Run: npx tsx scripts/test_world_sync.ts
 */

import { emptyRoomF2f } from "../src/utils/places";
import {
  agentsInPlace,
  applyWorldDelta,
  applyWorldSnapshot,
  emptyAgentInbox,
  normalizeAgentLocations,
  pushPlayerBubbleToRoom,
} from "../src/store/worldSync";
import type { TurnDelta, WorldSnapshot } from "../src/api/types";

class TestFailure extends Error {}

function ok(msg: string): void {
  console.log(`  ✓ ${msg}`);
}

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    throw new TestFailure(msg);
  }
}

function baseState() {
  return {
    placeId: "nvidia_reception",
    worldTick: 0,
    roomF2f: emptyRoomF2f(),
    agentLocations: {},
    agentInbox: {} as Record<string, ReturnType<typeof emptyAgentInbox>>,
    worldEvents: [],
    pendingWorldEvent: null,
  };
}

function test_room_f2f_per_place(): void {
  const delta: TurnDelta = {
    through_tick: 5,
    player_place_id: "nvidia_reception",
    room_f2f: {
      nvidia_reception: [
        { sender: "前台", content: "你好", type: "F2F", attempted_at: 2 },
      ],
      negotiation_room: [
        { sender: "Jensen", content: "私下", type: "F2F", attempted_at: 4 },
      ],
    },
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(baseState(), delta);
  assert(patch.roomF2f.nvidia_reception.length === 1, "reception F2F missing");
  assert(patch.roomF2f.negotiation_room.length === 1, "negotiation F2F missing");
  assert(patch.roomF2f.jensen_private_room.length === 0, "private room should be empty");
  ok("applyWorldDelta merges room_f2f per place");
}

function test_agent_inbox_and_player_location(): void {
  const delta: TurnDelta = {
    through_tick: 6,
    player_place_id: "nvidia_reception",
    agent_messages: {
      "3": {
        rdc: [
          {
            sender: "Jensen",
            content: "内参",
            type: "RDC",
            attempted_at: 3,
            sender_id: 2,
            recipient_id: 3,
          },
        ],
        grp: [],
      },
    },
    agent_locations: {
      "1": { place_id: "nvidia_reception", arrived_at: 0 },
      "2": { place_id: "negotiation_room", arrived_at: 4 },
    },
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(baseState(), delta);
  assert(patch.agentInbox["3"]?.rdc.length === 1, "agent 3 RDC missing");
  assert(patch.agentLocations.player?.placeId === "nvidia_reception", "player pseudo id missing");
  assert(
    agentsInPlace(patch.agentLocations, "nvidia_reception").includes("1"),
    "agent 1 should be at reception",
  );
  ok("applyWorldDelta agent inbox + player location + agentsInPlace");
}

function test_social_event_archive(): void {
  const delta: TurnDelta = {
    through_tick: 10,
    player_place_id: "nvidia_reception",
    social_events: [
      { at_tick: 10, kind: "group_leave", agent_id: 5, group_id: 100 },
    ],
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(baseState(), delta);
  const inbox = patch.agentInbox["5"];
  assert(inbox?.archivedThreadKeys.includes("grp:100"), "thread not archived");
  assert(
    inbox?.grp.some((m) => m.is_system && m.content.includes("退出")),
    "system leave message missing",
  );
  ok("applyWorldDelta archives group_leave with system message");
}

function test_world_events_queue(): void {
  const delta: TurnDelta = {
    through_tick: 8,
    player_place_id: "nvidia_reception",
    world_events: [
      {
        id: "broadcast_1",
        at_tick: 7,
        kind: "broadcast",
        content: "彭博快讯",
      },
    ],
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(baseState(), delta);
  assert(patch.pendingWorldEvent?.id === "broadcast_1", "pending world event missing");
  assert(patch.worldEvents.length === 1, "worldEvents length wrong");
  ok("applyWorldDelta queues world_events for modal");
}

function test_location_change_keys(): void {
  const delta: TurnDelta = {
    through_tick: 9,
    player_place_id: "nvidia_reception",
    location_changes: [
      {
        agent_id: 2,
        from_place: "negotiation_room",
        to_place: "jensen_private_room",
        at_tick: 8,
        source: "ipc_move",
      },
    ],
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(baseState(), delta);
  assert(patch.recentMoveKeys.includes("2:8"), "recentMoveKeys missing move");
  ok("applyWorldDelta records location_changes for animation");
}

function test_world_snapshot(): void {
  const snapshot: WorldSnapshot = {
    through_tick: 12,
    player_place_id: "nvidia_reception",
    agent_locations: { "1": { place_id: "nvidia_reception", arrived_at: 0 } },
    place_attrs: {},
    relations: [],
    group_members: {},
    name_map: { "1": "接待前台" },
  };
  const snap = applyWorldSnapshot(snapshot);
  assert(snap.nameMap["1"] === "接待前台", "name_map missing");
  assert(snap.agentLocations.player?.placeId === "nvidia_reception", "player in snapshot");
  ok("applyWorldSnapshot normalizes locations + name_map");
}

function test_push_player_bubble(): void {
  const rooms = emptyRoomF2f();
  const next = pushPlayerBubbleToRoom(rooms, "nvidia_reception", {
    sender: "玩家",
    content: "测试台词",
    type: "F2F",
  });
  assert(next.nvidia_reception.length === 1, "player bubble not added");
  assert(next.nvidia_reception[0]?.sender === "玩家", "player sender wrong");
  ok("pushPlayerBubbleToRoom writes to player room");
}

function test_normalize_locations(): void {
  const raw = normalizeAgentLocations({
    "2": { place_id: "jensen_private_room", arrived_at: 8 },
  });
  assert(raw["2"]?.placeId === "jensen_private_room", "normalize failed");
  ok("normalizeAgentLocations");
}

function main(): number {
  console.log("F12 Phase 3 — worldSync unit tests");
  const tests = [
    test_normalize_locations,
    test_room_f2f_per_place,
    test_agent_inbox_and_player_location,
    test_social_event_archive,
    test_world_events_queue,
    test_location_change_keys,
    test_world_snapshot,
    test_push_player_bubble,
  ];
  const failures: string[] = [];
  for (const fn of tests) {
    try {
      fn();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      failures.push(`${fn.name}: ${msg}`);
      console.log(`  ✗ ${msg}`);
    }
  }
  if (failures.length) {
    console.log(`\nFAILED (${failures.length}):`);
    for (const item of failures) {
      console.log(`  - ${item}`);
    }
    return 1;
  }
  console.log("\nALL F12 PHASE 3 WORLDSYNC TESTS PASSED");
  return 0;
}

process.exit(main());
