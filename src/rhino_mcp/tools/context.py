"""Per-process runtime context shared by all tool modules.

Tools call :func:`runtime` to learn whether they should hit the in-memory
``rhino3dm`` document or the bridge. Tests construct a fresh context with
:func:`set_runtime` to swap modes deterministically.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from rhino_mcp.bridge.rhino_connection import BridgeClient
from rhino_mcp.utils.error_handling import connection_error
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode

log = get_logger("context")

# Test mode: when True, runtime() falls back to STANDALONE if _RUNTIME is unset.
_TESTING = False


@dataclass
class Runtime:
    mode: Mode
    bridge: BridgeClient | None

    def require_bridge(self) -> BridgeClient:
        if self.bridge is None:
            raise connection_error("bridge required for this tool")
        return self.bridge


_RUNTIME: Runtime | None = None
_LOCK = threading.Lock()


def set_runtime(mode: Mode, bridge: BridgeClient | None) -> None:
    global _RUNTIME
    with _LOCK:
        if _RUNTIME is not None and not _TESTING:
            log.warning("set_runtime() called twice (mode=%s → %s)", _RUNTIME.mode.value, mode.value)
        _RUNTIME = Runtime(mode=mode, bridge=bridge)


def runtime() -> Runtime:
    with _LOCK:
        if _RUNTIME is None:
            if _TESTING:
                return Runtime(mode=Mode.STANDALONE, bridge=None)
            raise RuntimeError(
                "runtime() called before set_runtime(). "
                "Call build_server() first, or set _TESTING=True in tests."
            )
        return _RUNTIME


def reset() -> None:
    """Clear runtime context (test helper)."""
    global _RUNTIME
    with _LOCK:
        _RUNTIME = None


def enable_testing() -> None:
    """Enable test mode (runtime() falls back to STANDALONE when _RUNTIME is unset)."""
    global _TESTING
    _TESTING = True


def disable_testing() -> None:
    """Disable test mode."""
    global _TESTING
    _TESTING = False
