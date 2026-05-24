"""Compatibility shim — implementation lives in core/runner/run_hbm.py."""

from agent_world.hbm_demo.core.runner.run_hbm import main

__all__ = ["main"]

if __name__ == "__main__":
    import sys

    sys.exit(main())
