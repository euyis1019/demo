"""Compatibility shim — implementation lives in core/runner/run_drama.py."""

from agent_world.drama_demo.core.runner.run_drama import main

__all__ = ["main"]

if __name__ == "__main__":
    import sys

    sys.exit(main())
