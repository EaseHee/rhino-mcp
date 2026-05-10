"""Per-process runtime context shared by all tool modules.

Tools call :func:`runtime` to learn whether they should hit the in-memory
``rhino3dm`` document or the bridge. Tests construct a fresh context with
:func:`set_runtime` to swap modes deterministically.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

from rhino_mcp.bridge.rhino_connection import BridgeClient
from rhino_mcp.utils.error_handling import connection_error
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode

log = get_logger("context")

# Test mode: when True, runtime() falls back to STANDALONE if _RUNTIME is unset.
_TESTING = False

# Minimum seconds between back-to-back bridge re-detection attempts.
_REDETECT_COOLDOWN = float(os.environ.get("RHINO_MCP_REDETECT_COOLDOWN", "5"))


@dataclass
class Runtime:
    mode: Mode
    bridge: BridgeClient | None
    _last_redetect_at: float = field(default=0.0, repr=False, compare=False)
    _promote_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def require_bridge(self) -> BridgeClient:
        """Return a live BridgeClient, attempting lazy promotion when needed.

        If the current client is dead or absent, a re-detection is attempted
        after the cooldown period. Raises connection_error when no bridge can
        be reached.
        """
        if self.bridge is not None:
            if self.bridge.is_alive():
                return self.bridge
            # Dead client — clean up and fall through to re-detection.
            try:
                self.bridge.close()
            except Exception:
                pass
            self.bridge = None
            self.mode = Mode.STANDALONE

        if time.monotonic() - self._last_redetect_at > _REDETECT_COOLDOWN:
            self._try_promote_to_bridge()

        if self.bridge is None:
            raise connection_error("bridge required for this tool")
        return self.bridge

    def _try_promote_to_bridge(self) -> None:
        """Attempt a non-blocking bridge re-detection; update mode on success."""
        with self._promote_lock:
            # Double-check: another thread may have just promoted.
            if time.monotonic() - self._last_redetect_at <= _REDETECT_COOLDOWN:
                return
            self._last_redetect_at = time.monotonic()

        client = BridgeClient.auto(timeout=2.0)
        if client is not None:
            log.info("Promoted runtime to BRIDGE on demand")
            self.bridge = client
            self.mode = Mode.BRIDGE


_RUNTIME: Runtime | None = None
_LOCK = threading.Lock()


def set_runtime(mode: Mode, bridge: BridgeClient | None) -> None:
    global _RUNTIME
    with _LOCK:
        if _RUNTIME is not None and not _TESTING:
            log.info("Runtime mode transition: %s → %s", _RUNTIME.mode.value, mode.value)
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
