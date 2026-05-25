/**
 * F12 synthetic scenario — replays fixture deltas through worldSync (no LLM, no Flask).
 * Run: npx tsx scripts/test_f12_synthetic_fixture.ts
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { TurnDelta, WorldSnapshot } from "../src/api/types";
import { emptyRoomF2f } from "../src/utils/places";
import {
  agentsInPlace,
  applyWorldDelta,
  applyWorldSnapshot,
  emptyAgentInbox,
  moveKeyForAgent,
} from "../src/store/worldSync";

const __dir = dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = join(
  __dir,
  "../../scripts/fixtures/f12_synthetic_fixture.json",
);

class TestFailure extends Error {}

function ok(msg: string): void {
  console.log(`  ✓ ${msg}`);
}

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    throw new TestFailure(msg);
  }
}

interface FixtureStep {
  name: string;
  delta: TurnDelta;
  expect: Record<string, unknown>;
}

interface Fixture {
  initial_state: { placeId: string; worldTick: number };
  deltas: FixtureStep[];
  snapshot: WorldSnapshot;
}

function loadFixture(): Fixture {
  return JSON.parse(readFileSync(FIXTURE_PATH, "utf-8")) as Fixture;
}

function baseFromFixture(fix: Fixture) {
  return {
    placeId: fix.initial_state.placeId,
    worldTick: fix.initial_state.worldTick,
    roomF2f: emptyRoomF2f(),
    agentLocations: {} as Record<string, { placeId: string; arrivedAt: number }>,
    agentInbox: {} as Record<string, ReturnType<typeof emptyAgentInbox>>,
    worldEvents: [],
    pendingWorldEvent: null as import("../src/api/types").WorldEvent | null,
  };
}

function mergeRoomF2f(
  current: ReturnType<typeof emptyRoomF2f>,
  partial: Partial<Record<string, import("../src/api/types").GameMessage[]>> | undefined,
): ReturnType<typeof emptyRoomF2f> {
  if (!partial) {
    return current;
  }
  const next = { ...current };
  for (const [place, msgs] of Object.entries(partial)) {
    if (msgs && place in next) {
      next[place as keyof typeof next] = [
        ...next[place as keyof typeof next],
        ...msgs,
      ];
    }
  }
  return next;
}

function runFixture(): void {
  const fix = loadFixture();
  let state = baseFromFixture(fix);

  for (const step of fix.deltas) {
    const delta: TurnDelta = {
      public_messages: [],
      observer_messages: [],
      group_messages: [],
      ...step.delta,
      room_f2f: mergeRoomF2f(state.roomF2f, step.delta.room_f2f),
    };
    const patch = applyWorldDelta(state, delta);
    state = { ...state, ...patch, recentMoveKeys: patch.recentMoveKeys };
    const exp = step.expect;

    if (step.name === "turn1_reception_f2f") {
      assert(
        state.roomF2f.nvidia_reception.length === exp.reception_f2f_count,
        "reception F2F count",
      );
      assert(
        state.roomF2f.negotiation_room.length === exp.negotiation_f2f_count,
        "negotiation F2F should be empty at turn1 window",
      );
      assert(
        (state.agentInbox["2"]?.rdc.length ?? 0) === exp.agent2_rdc_count,
        "agent2 RDC inbox",
      );
      assert(state.placeId === exp.player_place, "player place");
    }

    if (step.name === "node_a_jensen_private") {
      assert(
        moveKeyForAgent("2", state.recentMoveKeys ?? patch.recentMoveKeys),
        "Jensen move animation key",
      );
      assert(
        state.pendingWorldEvent?.kind === exp.pending_world_event_kind,
        "routing world event",
      );
      assert(
        (state.agentInbox["2"]?.osLog.length ?? 0) === exp.state_os_count,
        "inner OS timeline",
      );
      assert(
        state.agentLocations["2"]?.placeId === exp.jensen_place,
        "Jensen at private room",
      );
    }

    if (step.name === "turn16_broadcast_and_group_leave") {
      const inbox5 = state.agentInbox["5"];
      assert(inbox5?.archivedThreadKeys.includes("grp:100"), "group thread archived");
      assert(
        inbox5?.grp.some((m) => m.is_system && m.content.includes("退出")),
        "group leave system message",
      );
      const broadcasts = state.worldEvents.filter((e) => e.kind === "broadcast");
      assert(broadcasts.length >= 1, "broadcast queued in worldEvents");
      ok(`fixture step: ${step.name}`);
      continue;
    }

    if (step.name === "node_c_ceos_reception") {
      const atReception = agentsInPlace(state.agentLocations, "nvidia_reception");
      for (const id of exp.reception_agents_include as string[]) {
        assert(atReception.includes(id), `agent ${id} should be at reception`);
      }
      assert(
        patch.recentMoveKeys.length === exp.location_change_count,
        "CEO move keys",
      );
    }

    ok(`fixture step: ${step.name}`);
  }

  const snapPatch = applyWorldSnapshot(fix.snapshot);
  assert(snapPatch.nameMap["1"] === "接待前台", "snapshot name_map");
  assert(
    agentsInPlace(snapPatch.agentLocations, "nvidia_reception").includes("4"),
    "snapshot CEO at reception",
  );
  ok("applyWorldSnapshot calibration from fixture");
}

function main(): number {
  console.log("F12 synthetic fixture — frontend worldSync replay");
  try {
    runFixture();
  } catch (err) {
    console.log(`  ✗ ${err instanceof Error ? err.message : err}`);
    return 1;
  }
  console.log("\nALL F12 SYNTHETIC FIXTURE TESTS PASSED");
  return 0;
}

process.exit(main());
