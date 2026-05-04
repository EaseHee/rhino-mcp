"""Bridge mode detection and JSON-RPC client.

Detection strategy:

1. Read ``RHINO_MCP_FORCE_MODE`` (``standalone`` | ``bridge``) — explicit override.
2. Pick a transport candidate based on platform (named pipe → unix socket → TCP).
3. Try to ``connect`` and send a ``rhino.ping`` JSON-RPC; if it succeeds within
   the timeout, mode is BRIDGE; otherwise STANDALONE.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import threading
import time
import uuid
from typing import Any

from rhino_mcp.bridge.named_pipe import NamedPipeTransport
from rhino_mcp.bridge.tcp_socket import TcpTransport
from rhino_mcp.bridge.transport_base import Transport
from rhino_mcp.bridge.unix_socket import UnixSocketTransport, default_socket_path
from rhino_mcp.utils.error_handling import ToolError, connection_error
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode

log = get_logger("bridge")

_MAX_RECONNECT_RETRIES = int(os.environ.get("RHINO_MCP_RECONNECT_RETRIES", "1"))
_RECONNECT_BASE_DELAY = float(os.environ.get("RHINO_MCP_RECONNECT_BASE_DELAY", "0.5"))
# Jitter ratio (±). 0 disables jitter (useful for deterministic tests).
_RECONNECT_JITTER = float(os.environ.get("RHINO_MCP_RECONNECT_JITTER", "0.25"))


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with optional symmetric jitter.

    Returns ``base * 2**attempt * (1 + uniform(-jitter, +jitter))``,
    clamped to a non-negative value. Jitter is disabled when
    ``RHINO_MCP_RECONNECT_JITTER=0`` (used in tests).
    """
    base: float = _RECONNECT_BASE_DELAY * (2 ** attempt)
    if _RECONNECT_JITTER <= 0:
        return base
    jittered: float = base * (1.0 + random.uniform(-_RECONNECT_JITTER, _RECONNECT_JITTER))
    return max(0.0, jittered)


def candidate_transports() -> list[Transport]:
    """Return platform-appropriate transports in priority order."""
    explicit = os.environ.get("RHINO_MCP_TRANSPORT_KIND", "").lower()
    host = os.environ.get("RHINO_HOST", "localhost")
    port = int(os.environ.get("RHINO_PORT", "4242"))
    if explicit == "tcp":
        return [TcpTransport(host, port)]
    if explicit == "pipe":
        return [NamedPipeTransport()]
    if explicit == "unix":
        return [UnixSocketTransport()]
    if sys.platform == "win32":
        return [NamedPipeTransport(), TcpTransport(host, port)]
    if sys.platform.startswith(("linux", "darwin")):
        sock_path = default_socket_path()
        candidates: list[Transport] = []
        if sock_path.exists():
            candidates.append(UnixSocketTransport(sock_path))
        candidates.append(TcpTransport(host, port))
        return candidates
    return [TcpTransport(host, port)]


class BridgeClient:
    """Synchronous JSON-RPC 2.0 client over a single transport.

    Thread-safe: callers may invoke from multiple worker threads; requests are
    serialised on a lock. The bridge plugin marshals all calls onto Rhino's UI
    thread, so sequential dispatch matches Rhino's threading model.
    """

    def __init__(self, transport: Transport, timeout: float = 30.0) -> None:
        self._transport = transport
        self._timeout = timeout
        self._lock = threading.Lock()
        self._connected = False
        self._max_retries = _MAX_RECONNECT_RETRIES

    @classmethod
    def auto(cls, timeout: float = 5.0) -> BridgeClient | None:
        """Try each candidate transport. Return a connected client or ``None``."""
        for t in candidate_transports():
            try:
                t.connect(timeout=timeout)
            except ConnectionError as exc:
                log.debug("Transport %s unavailable: %s", t.name, exc)
                continue
            client = cls(t, timeout=timeout)
            client._connected = True
            try:
                pong = client.call("rhino.ping", {})
                log.info("Bridge connected via %s (rhino=%s)", t.name, pong.get("rhino"))
                return client
            except Exception as exc:
                log.debug("Bridge ping on %s failed: %s", t.name, exc)
                t.close()
        return None

    @property
    def transport_name(self) -> str:
        return self._transport.name

    @property
    def is_healthy(self) -> bool:
        """Return True while the client believes its transport is connected."""
        return self._connected

    def close(self) -> None:
        self._transport.close()
        self._connected = False

    def ping(self, timeout: float = 2.0) -> bool:
        """Send a ``rhino.ping`` to verify the bridge is reachable."""
        if not self._connected:
            return False
        try:
            self._call_once("rhino.ping", {}, timeout=timeout)
            return True
        except Exception:
            return False

    def reconnect(self) -> bool:
        """Close and re-open the underlying transport, then re-ping."""
        log.info("Attempting reconnect on %s", self._transport.name)
        try:
            self._transport.close()
        except Exception:
            pass
        self._connected = False
        try:
            self._transport.connect(timeout=self._timeout)
            self._connected = True
            pong = self._call_once("rhino.ping", {})
            log.info("Reconnected via %s (rhino=%s)", self._transport.name, pong.get("rhino"))
            return True
        except Exception as exc:
            log.warning("Reconnect failed: %s", exc)
            self._connected = False
            return False

    def is_alive(self) -> bool:
        """Cheap, non-destructive liveness probe via the underlying transport."""
        if not self._connected:
            return False
        return self._transport.is_alive()

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and return its result, raising ToolError on RPC error.

        On transport failure the client retries up to ``_max_retries`` times
        with exponential backoff plus optional symmetric jitter (controlled
        by ``RHINO_MCP_RECONNECT_JITTER``).
        """
        try:
            return self._call_once(method, params)
        except ToolError as exc:
            if exc.category.value != "connection":
                raise
            # Retry with reconnect.
            for attempt in range(self._max_retries):
                delay = _backoff_delay(attempt)
                log.info(
                    "Reconnect attempt %d/%d (delay=%.2fs)",
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                time.sleep(delay)
                if self.reconnect():
                    return self._call_once(method, params)
            raise

    async def async_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Async variant of :meth:`call`; offloads the blocking I/O to a thread."""
        return await asyncio.to_thread(self.call, method, params)

    def _call_once(self, method: str, params: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        """Single JSON-RPC round-trip without retry/reconnect."""
        if not self._connected:
            raise connection_error(f"transport {self._transport.name} not connected")
        request_id = uuid.uuid4().hex
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        payload = json.dumps(request, separators=(",", ":")).encode("utf-8")
        effective_timeout = timeout if timeout is not None else self._timeout
        try:
            with self._lock:
                self._transport.send_line(payload)
                line = self._transport.recv_line(timeout=effective_timeout)
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._connected = False
            self._transport.close()
            raise connection_error(f"transport failure on {self._transport.name}: {exc}") from exc
        try:
            response = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            truncated = line[:200] if len(line) > 200 else line
            raise connection_error(f"non-JSON response: {truncated!r}") from exc
        if response.get("id") != request_id:
            raise connection_error(
                f"request ID mismatch (expected={request_id}, got={response.get('id')})"
            )
        if "error" in response:
            err = response["error"]
            from rhino_mcp.utils.error_handling import ErrorCategory
            raise ToolError(
                ErrorCategory.INTERNAL,
                f"Bridge error: {err.get('message','unknown')}",
                err.get("data", {}).get("hint", "Check Rhino's command-line for stack traces."),
                details=err,
            )
        return response.get("result", {})


def detect_mode() -> tuple[Mode, BridgeClient | None]:
    """Detect runtime mode and return ``(mode, client_or_none)``.

    When ``RHINO_MCP_BRIDGE_OPTIONAL=1`` is set together with
    ``RHINO_MCP_FORCE_MODE=bridge``, a failed bridge connection falls back to
    standalone instead of raising.  This is the default behaviour for connector
    (HTTP) deployments where Rhino may not be running at server start-up.
    """
    forced = os.environ.get("RHINO_MCP_FORCE_MODE", "").lower()
    optional = os.environ.get("RHINO_MCP_BRIDGE_OPTIONAL", "0") == "1"

    if forced == "standalone":
        log.info("RHINO_MCP_FORCE_MODE=standalone")
        return Mode.STANDALONE, None

    if forced == "bridge":
        log.info("RHINO_MCP_FORCE_MODE=bridge — attempting bridge")
        client = BridgeClient.auto(timeout=float(os.environ.get("RHINO_MCP_BRIDGE_TIMEOUT", "5")))
        if client is None:
            if optional:
                log.warning(
                    "Bridge unreachable (RHINO_MCP_BRIDGE_OPTIONAL=1); "
                    "falling back to standalone mode. "
                    "Start Rhino 8 with the rhino-mcp.rhp C# plugin loaded, then restart to enable bridge tools."
                )
                return Mode.STANDALONE, None
            raise connection_error(
                "RHINO_MCP_FORCE_MODE=bridge but no bridge transport accepted ping"
            )
        return Mode.BRIDGE, client

    client = BridgeClient.auto(timeout=float(os.environ.get("RHINO_MCP_BRIDGE_TIMEOUT", "1")))
    if client is not None:
        return Mode.BRIDGE, client
    log.info("No bridge reachable; running in standalone (rhino3dm) mode.")
    return Mode.STANDALONE, None
