import type { GameMessage } from "../src/api/types";
import { PLAYER_SENDER } from "../src/constants/gameLoop";
import { createInitialState, gameReducer } from "../src/store/gameStore";
import {
  mergeMessages,
  sortMessages,
  stampPlayerBubble,
} from "../src/utils/messages";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function msg(
  sender: string,
  content: string,
  attempted_at?: number,
): GameMessage {
  return { type: "F2F", sender, content, attempted_at };
}

function senders(messages: GameMessage[]): string[] {
  return messages.map((m) => `${m.sender}@${m.attempted_at ?? "?"}`);
}

// --- unit: stamp + sort ---
let state: GameMessage[] = [];
state = mergeMessages(state, [
  stampPlayerBubble(state, msg(PLAYER_SENDER, "turn1 player")),
]);
assert(state[0].attempted_at === 0.5, "turn1 player should be 0.5");

state = mergeMessages(state, [
  msg("接待前台", "turn1 agent a", 3),
  msg("Sam Altman", "turn1 agent b", 4),
  msg("接待前台", "turn1 agent c", 5),
]);
assert(
  senders(state).join(" | ") ===
    "玩家@0.5 | 接待前台@3 | Sam Altman@4 | 接待前台@5",
  `turn1 order wrong: ${senders(state).join(" | ")}`,
);

state = mergeMessages(state, [
  stampPlayerBubble(state, msg(PLAYER_SENDER, "turn2 player")),
]);
const turn2Player = state.find((m) => m.content === "turn2 player");
assert(turn2Player?.attempted_at === 5.5, "turn2 player should be 5.5");

state = mergeMessages(state, [
  msg("接待前台", "turn2 agent a", 8),
  msg("Sam Altman", "turn2 agent b", 9),
]);
const fullOrder = senders(state).join(" | ");
assert(
  fullOrder ===
    "玩家@0.5 | 接待前台@3 | Sam Altman@4 | 接待前台@5 | 玩家@5.5 | 接待前台@8 | Sam Altman@9",
  `full two-turn order wrong: ${fullOrder}`,
);

// --- reducer: two-turn simulation ---
let game = createInitialState();
game = gameReducer(game, {
  type: "PUSH_PLAYER_BUBBLE",
  message: msg(PLAYER_SENDER, "p1"),
});
game = gameReducer(game, {
  type: "APPEND_ACTION_RESULT",
  data: {
    status: "completed",
    task_id: "t1",
    end_tick: 4,
    current_phase: "Phase 1",
    stats_update: game.stats,
    public_messages: [
      msg("接待前台", "a1", 3),
      msg("Sam Altman", "a2", 4),
    ],
    observer_messages: [],
    group_messages: [],
  },
});
game = gameReducer(game, {
  type: "PUSH_PLAYER_BUBBLE",
  message: msg(PLAYER_SENDER, "p2"),
});
game = gameReducer(game, {
  type: "APPEND_ACTION_RESULT",
  data: {
    status: "completed",
    task_id: "t2",
    end_tick: 8,
    current_phase: "Phase 1",
    stats_update: game.stats,
    public_messages: [
      msg("接待前台", "a3", 7),
      msg("Sam Altman", "a4", 8),
    ],
    observer_messages: [],
    group_messages: [],
  },
});

const reducerOrder = game.f2fMessages.map(
  (m) => `${m.sender}:${m.content}@${m.attempted_at}`,
);
assert(
  reducerOrder.join(" -> ") ===
    "玩家:p1@0.5 -> 接待前台:a1@3 -> Sam Altman:a2@4 -> 玩家:p2@4.5 -> 接待前台:a3@7 -> Sam Altman:a4@8",
  `reducer order wrong: ${reducerOrder.join(" -> ")}`,
);

// tie-break: same attempted_at, player before NPC
const tied = sortMessages([
  msg("接待前台", "npc", 2),
  msg(PLAYER_SENDER, "player", 2),
]);
assert(
  tied[0].sender === PLAYER_SENDER,
  "player should sort before NPC at same attempted_at",
);

console.log("verify_f2f_order: all checks passed");
