"""Bridge mode detection and JSON-RPC client.

Detection strategy:

1. Read ``RHINO_MCP_FORCE_MODE`` (``standalone`` | ``bridge``) — explicit override.
2. Pick a transport candidate based on platform (named pipe → unix socket → TCP).
3. Try to ``connect`` and send a ``rhino.ping`` JSON-RPC; if it succeeds within
   the timeout, mode is BRIDGE; otherwise STANDALONE.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
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

_MAX_RECONNECT_RETRIES = int(os.environ.get("RHINO_MCP_RECONNECT_RETRIES", "3"))
_RECONNECT_BASE_DELAY = float(os.environ.get("RHINO_MCP_RECONNECT_BASE_DELAY", "0.5"))
# Jitter ratio (±). 0 disables jitter (useful for deterministic tests).
_RECONNECT_JITTER = float(os.environ.get("RHINO_MCP_RECONNECT_JITTER", "0.25"))

# Minimum bridge protocol version this client understands. The C# plugin
# advertises ``protocol_version`` in its ``rhino.ping`` reply (added in
# v0.4.2). Older plugins omit the field; we treat that as "0" and warn
# without aborting so existing deployments keep working.
_REQUIRED_PROTOCOL_VERSION = "1.0"

# Honour ``RHINO_MCP_GZIP=0`` to disable opt-in response compression. The
# bridge falls back to plain JSON when the flag is empty / 0 / "off".
def _gzip_enabled() -> bool:
    raw = os.environ.get("RHINO_MCP_GZIP", "1").lower()
    return raw not in {"0", "false", "off", "no", ""}


def _check_protocol(pong: dict[str, Any], transport_name: str) -> None:
    """Log a warning when the bridge advertises an older protocol version."""
    advertised = str(pong.get("protocol_version", "0"))
    try:
        ours = tuple(int(x) for x in _REQUIRED_PROTOCOL_VERSION.split("."))
        theirs = tuple(int(x) for x in advertised.split("."))
    except ValueError:
        return
    if theirs < ours:
        log.warning(
            "Bridge on %s advertises protocol_version=%s (client expects >=%s). "
            "Some stability fixes from v0.4.2 require the matching plugin build.",
            transport_name, advertised, _REQUIRED_PROTOCOL_VERSION,
        )


def _decompress_payload(meta: dict[str, Any]) -> dict[str, Any]:
    """Inverse of the bridge's gzip path. Decode and parse the inner JSON."""
    encoding = str(meta.get("encoding", "")).lower()
    raw = meta.get("data_b64")
    if encoding != "gzip" or not isinstance(raw, str):
        raise connection_error(f"unsupported compressed payload: {meta!r}")
    try:
        blob = base64.b64decode(raw)
        text = gzip.decompress(blob).decode("utf-8")
        decoded = json.loads(text)
    except Exception as exc:
        raise connection_error(f"failed to decompress payload: {exc}") from exc
    if not isinstance(decoded, dict):
        raise connection_error("decompressed payload is not a JSON object.")
    return decoded


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
                _check_protocol(pong, t.name)
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
            self._transport.reset_buffers()
        except Exception:
            pass
        try:
            self._transport.connect(timeout=self._timeout)
            self._connected = True
            pong = self._call_once("rhino.ping", {})
            log.info("Reconnected via %s (rhino=%s)", self._transport.name, pong.get("rhino"))
            _check_protocol(pong, self._transport.name)
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
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        if _gzip_enabled():
            request["_accept_encoding"] = ["gzip"]
        payload = json.dumps(request, separators=(",", ":")).encode("utf-8")
        effective_timeout = timeout if timeout is not None else self._timeout
        try:
            with self._lock:
                self._transport.send_line(payload)
                # Server may interleave heartbeat notifications (no `id`) ahead
                # of the response while a long-running handler runs.  Drain
                # them until a response with the matching id arrives — but
                # respect a single deadline derived from `effective_timeout`
                # so a chatty notification stream cannot stretch the
                # round-trip past what the caller asked for.
                deadline = time.monotonic() + effective_timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"bridge response did not arrive within {effective_timeout}s "
                            "(only notification frames received)"
                        )
                    line = self._transport.recv_line(timeout=remaining)
                    try:
                        candidate = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        # Defer reporting to the post-lock path below so the
                        # error message can include the truncated payload.
                        response = None
                        break
                    if "id" not in candidate or candidate.get("id") is None:
                        # Notification frame (heartbeat) — log once at debug and skip.
                        if candidate.get("method") != "rhino.heartbeat":
                            log.debug("ignoring server notification: %s", candidate.get("method"))
                        continue
                    response = candidate
                    break
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._connected = False
            # Drop any partially-buffered bytes before tearing down the
            # underlying socket. Otherwise a stale half-line would survive
            # into the next reconnect attempt and corrupt framing.
            try:
                self._transport.reset_buffers()
            except Exception:
                pass
            self._transport.close()
            raise connection_error(f"transport failure on {self._transport.name}: {exc}") from exc
        if response is None:
            truncated = line[:200] if len(line) > 200 else line
            raise connection_error(f"non-JSON response: {truncated!r}")
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
        result = response.get("result", {})
        if isinstance(result, dict) and result.get("__chunked__") is True:
            result = self._reassemble_chunked(result, effective_timeout)
        if isinstance(result, dict) and result.get("__compressed__") is True:
            result = _decompress_payload(result)
        return result

    def _reassemble_chunked(self, meta: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Pull all chunk slices, concatenate, and parse as the original result."""
        chunk_id = str(meta.get("chunk_id"))
        total = int(meta.get("total_chunks", 0))
        encoding = str(meta.get("encoding", "json"))
        if not chunk_id or total <= 0:
            raise connection_error(f"invalid chunked metadata: {meta!r}")
        log.debug(
            "Reassembling chunked response chunk_id=%s total=%d size=%s",
            chunk_id, total, meta.get("size"),
        )
        parts: list[bytes] = []
        try:
            for index in range(total):
                slice_resp = self._call_once(
                    "rhino.bridge.fetch_chunk",
                    {"chunk_id": chunk_id, "index": index},
                    timeout=timeout,
                )
                parts.append(base64.b64decode(slice_resp["data_b64"]))
                if slice_resp.get("is_last") and index + 1 != total:
                    break
        finally:
            try:
                self._call_once(
                    "rhino.bridge.chunk_release",
                    {"chunk_id": chunk_id},
                    timeout=timeout,
                )
            except Exception:
                pass
        blob = b"".join(parts)
        if encoding != "json":
            raise connection_error(f"unsupported chunk encoding: {encoding}")
        try:
            return json.loads(blob.decode("utf-8"))
        except json.JSONDecodeError as exc:
            truncated = blob[:200]
            raise connection_error(f"chunked payload not valid JSON: {truncated!r}") from exc


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

    client = BridgeClient.auto(timeout=float(os.environ.get("RHINO_MCP_BRIDGE_TIMEOUT", "5")))
    if client is not None:
        return Mode.BRIDGE, client
    log.info("No bridge reachable; running in standalone (rhino3dm) mode.")
    return Mode.STANDALONE, None
