"""F00 platform core — Runner process (kernel, agents, IPC).

Import submodules directly (e.g. ``core.runner.kernel``) to avoid eager
cross-feature imports through ``ipc_handlers``.
"""

from agent_world.drama_demo.core.runner.drama_agent import DramaAgent
from agent_world.drama_demo.core.runner.kernel import (
    DramaKernel,
    MinimalKernel,
    build_kernel,
    build_minimal_kernel,
    resolve_api_key,
)
from agent_world.drama_demo.core.runner.seed import seed_world
from agent_world.drama_demo.core.runner.world_step import DramaWorldStep

__all__ = [
    "DramaAgent",
    "DramaKernel",
    "MinimalKernel",
    "DramaWorldStep",
    "build_kernel",
    "build_minimal_kernel",
    "resolve_api_key",
    "seed_world",
]
