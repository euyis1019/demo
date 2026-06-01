#!/usr/bin/env bash
# Wrapper — delegates to scripts/ops/stop_demo.sh (dev_logs/38 Phase R1).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ops/stop_demo.sh" "$@"
