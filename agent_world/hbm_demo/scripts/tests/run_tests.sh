#!/usr/bin/env bash
# Run M0–M7 acceptance tests (dev_logs/38 Phase R1).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT"
exec python3 agent_world/hbm_demo/scripts/tests/test_m0.py "$@"
