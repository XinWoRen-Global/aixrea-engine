"""Pluggable memory for DeerFlow.

The shared, backend-agnostic core: the :class:`MemoryManager` contract, the
:func:`get_memory_manager` singleton factory, and :func:`reset_memory_manager`.
Backends live under :mod:`backends` (each self-contained, exposing
``MANAGER_CLASS``); the default DeerMem backend's functional modules live in
``backends/deermem/core/``. Swap backend = drop a ``backends/<name>/`` folder +
set ``MemoryConfig.manager_class`` -- nothing else in deer-flow changes.

DeerMem-private symbols (``format_memory_for_injection``, ``get_memory_data``,
``MemoryUpdater``, ``FileMemoryStorage``, ...) are NOT re-exported here -- import
them directly from ``deerflow.agents.memory.backends.deermem.deermem.core.*``.
"""

from deerflow.agents.memory.manager import (
    MemoryConflictError,
    MemoryCorruptionError,
    MemoryManager,
    MemoryManagerError,
    MemoryReadError,
    get_memory_manager,
    memory_read_failures_are_fatal,
    reset_memory_manager,
)

# 团队记忆（Team Memory）— 可选导入，不依赖 DeerMem 后端
try:
    from deerflow.agents.memory.memory_assembly import MemoryAssembly, get_memory_assembly
    from deerflow.agents.memory.team_memory import TeamMemoryManager, get_team_memory_manager

    _team_memory_available = True
except ImportError:
    _team_memory_available = False

__all__ = [
    "MemoryManager",
    "MemoryManagerError",
    "MemoryReadError",
    "MemoryConflictError",
    "MemoryCorruptionError",
    "MemoryReadError",
    "get_memory_manager",
    "memory_read_failures_are_fatal",
    "reset_memory_manager",
    "TeamMemoryManager",
    "get_team_memory_manager",
    "MemoryAssembly",
    "get_memory_assembly",
    "_team_memory_available",
]
