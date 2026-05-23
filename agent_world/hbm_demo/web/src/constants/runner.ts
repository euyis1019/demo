/** 本地启动命令 — PLAN2 F5-2 / dev_docs §〇 / README。 */

export const RUN_HBM_COMMAND = `python -m agent_world.hbm_demo.run_hbm \\
  --config agent_world/hbm_demo/hbm_scenario.yaml \\
  --sim-dir agent_world/hbm_demo/sim/hbm_memory_war/`;

export const POLL_TIMEOUT_MESSAGE =
  "轮询超时（120 次 × 1.5s），NPC 响应未完成。请确认 Runner 仍在运行后重新发送台词。";
