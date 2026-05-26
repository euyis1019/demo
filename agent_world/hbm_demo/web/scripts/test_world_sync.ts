/**
 * F12 Phase 3 — worldSync merge unit tests (dev_logs/32 §6.5–6.6).
 * Run: npx tsx scripts/test_world_sync.ts
 */

import { computeNextSinceTick } from "../src/features/game-loop/worldDeltaApply";
import { deltaSinceTickForSession } from "../src/features/game-loop/hydrateWorldSnapshot";
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
    processedWorldEventIds: [] as string[],
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
  assert(next.nvidia_reception[0]?._optimistic === true, "player bubble should be optimistic");
  ok("pushPlayerBubbleToRoom writes to player room");
}

function test_player_f2f_optimistic_delta_dedupe(): void {
  const state = {
    ...baseState(),
    roomF2f: pushPlayerBubbleToRoom(emptyRoomF2f(), "nvidia_reception", {
      sender: "玩家",
      content: "你好，我来谈 HBM 显存降本方案。",
      type: "F2F",
    }),
  };
  const delta: TurnDelta = {
    through_tick: 3,
    player_place_id: "nvidia_reception",
    room_f2f: {
      nvidia_reception: [
        {
          sender: "玩家",
          content: "你好，我来谈 HBM 显存降本方案。",
          type: "F2F",
          attempted_at: 3,
          sender_id: 0,
          ref_key: "f2f:42",
        },
      ],
    },
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(state, delta);
  const msgs = patch.roomF2f.nvidia_reception;
  assert(msgs.length === 1, `player F2F should dedupe optimistic+delta, got ${msgs.length}`);
  assert(msgs[0]?.ref_key === "f2f:42", "deduped message should keep ref_key from delta");
  assert(!msgs[0]?._optimistic, "confirmed player message should not stay optimistic");
  ok("optimistic player bubble merges with world-delta F2F (no duplicate)");
}

function test_player_f2f_room_and_public_messages_dedupe(): void {
  const delta: TurnDelta = {
    through_tick: 8,
    player_place_id: "nvidia_reception",
    room_f2f: {
      nvidia_reception: [
        {
          sender: "玩家",
          content: "我带了 benchmark 数据和客户意向书，技术细节可以当场展开。",
          type: "F2F",
          attempted_at: 8,
          sender_id: 0,
          ref_key: "f2f:99",
        },
      ],
    },
    public_messages: [
      {
        sender: "玩家",
        content: "我带了 benchmark 数据和客户意向书，技术细节可以当场展开。",
        type: "F2F",
        attempted_at: 8,
        sender_id: 0,
        ref_key: "f2f:99",
      },
    ],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(baseState(), delta);
  const msgs = patch.roomF2f.nvidia_reception;
  assert(
    msgs.length === 1,
    `room_f2f + public_messages should not duplicate player line, got ${msgs.length}`,
  );
  ok("room_f2f + legacy public_messages dedupe player F2F");
}

function test_player_f2f_optimistic_then_public_messages_dedupe(): void {
  const state = {
    ...baseState(),
    roomF2f: pushPlayerBubbleToRoom(emptyRoomF2f(), "nvidia_reception", {
      sender: "玩家",
      content: "我带了 benchmark 数据和客户意向书，技术细节可以当场展开。",
      type: "F2F",
    }),
  };
  const delta: TurnDelta = {
    through_tick: 8,
    player_place_id: "nvidia_reception",
    room_f2f: {
      nvidia_reception: [
        {
          sender: "玩家",
          content: "我带了 benchmark 数据和客户意向书，技术细节可以当场展开。",
          type: "F2F",
          attempted_at: 8,
          sender_id: 0,
          ref_key: "f2f:99",
        },
      ],
    },
    public_messages: [
      {
        sender: "玩家",
        content: "我带了 benchmark 数据和客户意向书，技术细节可以当场展开。",
        type: "F2F",
        attempted_at: 8,
        sender_id: 0,
        ref_key: "f2f:99",
      },
    ],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(state, delta);
  const msgs = patch.roomF2f.nvidia_reception;
  assert(
    msgs.length === 1,
    `optimistic + room_f2f + public_messages should stay one player line, got ${msgs.length}`,
  );
  assert(msgs[0]?.ref_key === "f2f:99", "deduped player line keeps ref_key");
  ok("optimistic + room_f2f + public_messages dedupe player F2F");
}

function test_player_f2f_dedupe_across_tick_gap(): void {
  const state = {
    ...baseState(),
    roomF2f: pushPlayerBubbleToRoom(emptyRoomF2f(), "nvidia_reception", {
      sender: "玩家",
      content: "黄总那边还要多久？",
      type: "F2F",
      place_id: "nvidia_reception",
    }),
  };
  const delta: TurnDelta = {
    through_tick: 65,
    player_place_id: "nvidia_reception",
    room_f2f: {
      nvidia_reception: [
        {
          sender: "玩家",
          content: "黄总那边还要多久？",
          type: "F2F",
          attempted_at: 65,
          sender_id: 0,
          place_id: "nvidia_reception",
        },
      ],
    },
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(state, delta);
  assert(
    patch.roomF2f.nvidia_reception.length === 1,
    `player F2F should dedupe across tick gap, got ${patch.roomF2f.nvidia_reception.length}`,
  );
  ok("player F2F dedupes optimistic bubble vs later backend tick");
}

function test_world_events_not_requeued_after_processed(): void {
  const first: TurnDelta = {
    through_tick: 8,
    player_place_id: "nvidia_reception",
    world_events: [
      {
        id: "route_node_A",
        at_tick: 7,
        kind: "phase_route",
        content: "Phase 2 开始",
      },
    ],
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch1 = applyWorldDelta(baseState(), first);
  assert(patch1.pendingWorldEvent?.id === "route_node_A", "first route event missing");
  const replay: TurnDelta = {
    through_tick: 9,
    player_place_id: "nvidia_reception",
    world_events: [
      {
        id: "route_node_A",
        at_tick: 7,
        kind: "phase_route",
        content: "Phase 2 开始",
      },
    ],
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch2 = applyWorldDelta(
    {
      ...baseState(),
      worldEvents: patch1.worldEvents,
      pendingWorldEvent: patch1.pendingWorldEvent,
      processedWorldEventIds: patch1.processedWorldEventIds,
    },
    replay,
  );
  assert(
    patch2.worldEvents.length === 1,
    `replayed route event should not duplicate, got ${patch2.worldEvents.length}`,
  );
  assert(
    patch2.pendingWorldEvent?.id === "route_node_A",
    "pending modal should stay on first unseen event",
  );
  ok("world_events skip already-processed ids on delta replay");
}

function test_normalize_locations(): void {
  const raw = normalizeAgentLocations({
    "2": { place_id: "jensen_private_room", arrived_at: 8 },
  });
  assert(raw["2"]?.placeId === "jensen_private_room", "normalize failed");
  ok("normalizeAgentLocations");
}

function test_virtual_player_not_duplicated_in_grid(): void {
  const delta: TurnDelta = {
    through_tick: 3,
    player_place_id: "nvidia_reception",
    agent_locations: {
      "0": { place_id: "nvidia_reception", arrived_at: 0 },
      "1": { place_id: "nvidia_reception", arrived_at: 0 },
    },
    public_messages: [],
    observer_messages: [],
    group_messages: [],
  };
  const patch = applyWorldDelta(baseState(), delta);
  const atReception = agentsInPlace(patch.agentLocations, "nvidia_reception");
  assert(!atReception.includes("0"), "virtual player 0 should not appear in grid");
  assert(atReception.includes("player"), "UI player pseudo-id missing");
  assert(atReception.includes("1"), "receptionist missing");
  assert(atReception.length === 2, `expected 2 agents at reception, got ${atReception.length}`);
  ok("virtual player agent 0 excluded from room grid");
}

function test_delta_since_tick_for_session(): void {
  assert(deltaSinceTickForSession(0) === 0, "start 0 → cursor 0");
  assert(deltaSinceTickForSession(5) === 4, "start 5 → cursor 4 for RDC boundary");
  ok("deltaSinceTickForSession backs up one tick");
}

function test_compute_next_since_tick_running() {
  const partialPlayerOnly = {
    through_tick: 3,
    loop_state: "running",
    room_f2f: {
      nvidia_reception: [
        {
          sender: "玩家",
          content: "你好",
          type: "F2F" as const,
          attempted_at: 3,
          sender_id: 0,
        },
      ],
    },
  };
  const next = computeNextSinceTick(partialPlayerOnly, 0);
  assert(next === 2, `running loop should not advance past through-1: ${next}`);
  ok("computeNextSinceTick keeps same tick while loop running");
}

function main(): number {
  console.log("F12 Phase 3 — worldSync unit tests");
  const tests = [
    test_normalize_locations,
    test_virtual_player_not_duplicated_in_grid,
    test_room_f2f_per_place,
    test_agent_inbox_and_player_location,
    test_social_event_archive,
    test_world_events_queue,
    test_location_change_keys,
    test_world_snapshot,
    test_push_player_bubble,
    test_player_f2f_optimistic_delta_dedupe,
    test_player_f2f_room_and_public_messages_dedupe,
    test_player_f2f_optimistic_then_public_messages_dedupe,
    test_player_f2f_dedupe_across_tick_gap,
    test_world_events_not_requeued_after_processed,
    test_delta_since_tick_for_session,
    test_compute_next_since_tick_running,
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
