"""Mode-detection tests."""

from __future__ import annotations

from typing import Any

import pytest

from rhino_mcp.bridge import rhino_connection
from rhino_mcp.utils.registry import Mode


def test_force_standalone(monkeypatch) -> None:
    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")
    mode, client = rhino_connection.detect_mode()
    assert mode is Mode.STANDALONE
    assert client is None


def test_default_falls_back_to_standalone_when_no_bridge(monkeypatch) -> None:
    monkeypatch.delenv("RHINO_MCP_FORCE_MODE", raising=False)
    monkeypatch.setattr(rhino_connection.BridgeClient, "auto", classmethod(lambda cls, timeout=1.0: None))
    mode, client = rhino_connection.detect_mode()
    assert mode is Mode.STANDALONE
    assert client is None


def test_force_bridge_raises_when_unreachable(monkeypatch) -> None:
    """RHINO_MCP_FORCE_MODE=bridge with no bridge available raises ToolError."""
    from rhino_mcp.utils.error_handling import ToolError

    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "bridge")
    monkeypatch.delenv("RHINO_MCP_BRIDGE_OPTIONAL", raising=False)
    monkeypatch.setattr(rhino_connection.BridgeClient, "auto", classmethod(lambda cls, timeout=5.0: None))
    with pytest.raises(ToolError):
        rhino_connection.detect_mode()


def test_force_bridge_optional_falls_back_to_standalone(monkeypatch) -> None:
    """RHINO_MCP_FORCE_MODE=bridge + RHINO_MCP_BRIDGE_OPTIONAL=1 → standalone fallback."""
    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "bridge")
    monkeypatch.setenv("RHINO_MCP_BRIDGE_OPTIONAL", "1")
    monkeypatch.setattr(rhino_connection.BridgeClient, "auto", classmethod(lambda cls, timeout=5.0: None))
    mode, client = rhino_connection.detect_mode()
    assert mode is Mode.STANDALONE
    assert client is None


def test_candidate_transports_explicit_kind(monkeypatch) -> None:
    monkeypatch.setenv("RHINO_MCP_TRANSPORT_KIND", "tcp")
    transports = rhino_connection.candidate_transports()
    assert len(transports) == 1
    assert "tcp://" in transports[0].name


def test_backoff_delay_is_exponential_without_jitter(monkeypatch) -> None:
    monkeypatch.setattr(rhino_connection, "_RECONNECT_BASE_DELAY", 0.5)
    monkeypatch.setattr(rhino_connection, "_RECONNECT_JITTER", 0.0)
    assert rhino_connection._backoff_delay(0) == 0.5
    assert rhino_connection._backoff_delay(1) == 1.0
    assert rhino_connection._backoff_delay(2) == 2.0


def test_backoff_delay_applies_symmetric_jitter(monkeypatch) -> None:
    monkeypatch.setattr(rhino_connection, "_RECONNECT_BASE_DELAY", 1.0)
    monkeypatch.setattr(rhino_connection, "_RECONNECT_JITTER", 0.25)
    samples = [rhino_connection._backoff_delay(0) for _ in range(50)]
    assert all(0.75 <= d <= 1.25 for d in samples)
    # With 50 samples and ±25% jitter, we should observe non-trivial variance.
    assert len(set(samples)) > 1


class _FakeTransport:
    name = "fake://"

    def __init__(self, alive: bool = True) -> None:
        self._alive = alive
        self.reset_calls = 0

    def connect(self, timeout=None):
        return None

    def send_line(self, payload):
        return None

    def recv_line(self, timeout=None):
        return b"{}"

    def reset_buffers(self) -> None:
        self.reset_calls += 1

    def close(self):
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive


def test_bridge_client_is_alive_reflects_transport_state() -> None:
    transport = _FakeTransport(alive=True)
    client = rhino_connection.BridgeClient(transport, timeout=1.0)
    # Until ``connect`` is observed via auto/reconnect, BridgeClient holds
    # ``_connected = False``; emulate the post-connect state directly.
    client._connected = True
    assert client.is_alive() is True
    transport._alive = False
    assert client.is_alive() is False
    client._connected = False
    assert client.is_alive() is False


class _FailingTransport(_FakeTransport):
    """Transport that raises on send to exercise the error path."""

    def __init__(self, exc: Exception) -> None:
        super().__init__(alive=True)
        self._exc = exc

    def send_line(self, payload):  # type: ignore[override]
        raise self._exc


def test_call_once_resets_buffers_on_send_failure() -> None:
    transport = _FailingTransport(ConnectionError("boom"))
    client = rhino_connection.BridgeClient(transport, timeout=1.0)
    client._connected = True
    from rhino_mcp.utils.error_handling import ToolError

    with pytest.raises(ToolError):
        client._call_once("rhino.ping", {})
    assert transport.reset_calls == 1
    assert client._connected is False


def test_reconnect_clears_buffer_before_connect(monkeypatch) -> None:
    transport = _FakeTransport(alive=True)
    client = rhino_connection.BridgeClient(transport, timeout=1.0)
    client._connected = False

    # Make _call_once short-circuit so reconnect() does not need a JSON line.
    monkeypatch.setattr(
        rhino_connection.BridgeClient,
        "_call_once",
        lambda self, *a, **kw: {"rhino": "8.0", "protocol_version": "1.1"},
    )
    assert client.reconnect() is True
    assert transport.reset_calls >= 1
    assert client._connected is True


def _capture_protocol_warnings(pong: dict[str, Any]) -> list[str]:
    """Drive ``_check_protocol`` while capturing the bridge logger directly.

    The ``rhino_mcp`` logger sets ``propagate=False`` so pytest's ``caplog``
    fixture (which attaches at the root logger) cannot see its warnings.
    Attach a list-backed handler to the bridge logger for the call instead.
    """
    import logging

    sink: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            sink.append(record)

    handler = _ListHandler(level=logging.WARNING)
    logger = logging.getLogger("rhino_mcp.bridge")
    logger.addHandler(handler)
    try:
        rhino_connection._check_protocol(pong, "fake://")
    finally:
        logger.removeHandler(handler)
    return [r.getMessage() for r in sink]


def test_check_protocol_warns_on_old_version() -> None:
    messages = _capture_protocol_warnings({"protocol_version": "0"})
    assert any("protocol_version" in m for m in messages)


def test_check_protocol_silent_on_matching_version() -> None:
    messages = _capture_protocol_warnings(
        {"protocol_version": rhino_connection._REQUIRED_PROTOCOL_VERSION}
    )
    assert not any("protocol_version" in m for m in messages)


def test_decompress_payload_round_trip() -> None:
    import base64
    import gzip
    import json

    inner = {"summary": {"rows": list(range(100))}, "text": "ok"}
    blob = gzip.compress(json.dumps(inner).encode("utf-8"))
    meta = {
        "__compressed__": True,
        "encoding": "gzip",
        "original_size": len(json.dumps(inner)),
        "compressed_size": len(blob),
        "data_b64": base64.b64encode(blob).decode("ascii"),
    }
    out = rhino_connection._decompress_payload(meta)
    assert out == inner


def test_chunked_response_is_reassembled_transparently(monkeypatch) -> None:
    """A `__chunked__` result triggers fetch_chunk + release calls."""
    import base64
    import json

    transport = _FakeTransport(alive=True)
    client = rhino_connection.BridgeClient(transport, timeout=1.0)
    client._connected = True

    final_result = {"summary": {"rows": list(range(50))}, "text": "ok"}
    blob = json.dumps(final_result).encode("utf-8")
    chunk_size = 32
    total = (len(blob) + chunk_size - 1) // chunk_size

    seen: list[tuple[str, dict]] = []

    def fake_call_once(self, method, params, timeout=None):
        seen.append((method, params))
        if method == "rhino.bridge.fetch_chunk":
            idx = params["index"]
            start = idx * chunk_size
            end = min(start + chunk_size, len(blob))
            return {
                "chunk_id": params["chunk_id"],
                "index": idx,
                "data_b64": base64.b64encode(blob[start:end]).decode("ascii"),
                "is_last": end >= len(blob),
            }
        if method == "rhino.bridge.chunk_release":
            return {"released": True}
        raise AssertionError(f"unexpected method: {method}")

    monkeypatch.setattr(rhino_connection.BridgeClient, "_call_once", fake_call_once)

    meta = {
        "__chunked__": True,
        "chunk_id": "abc-123",
        "size": len(blob),
        "chunk_size": chunk_size,
        "total_chunks": total,
        "encoding": "json",
        "original_method": "rhino.test",
    }
    out = client._reassemble_chunked(meta, timeout=1.0)
    assert out == final_result
    methods = [m for m, _ in seen]
    assert methods.count("rhino.bridge.fetch_chunk") == total
    assert methods.count("rhino.bridge.chunk_release") == 1


def test_tcp_transport_enables_so_keepalive() -> None:
    """SO_KEEPALIVE option survives the connect() handshake on real sockets."""
    import socket

    from rhino_mcp.bridge.tcp_socket import TcpTransport

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()

    t = TcpTransport(host, port)
    try:
        t.connect(timeout=1.0)
        peer, _ = listener.accept()
        try:
            assert t._sock is not None
            ok = t._sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
            assert ok != 0
        finally:
            peer.close()
    finally:
        t.close()
        listener.close()
