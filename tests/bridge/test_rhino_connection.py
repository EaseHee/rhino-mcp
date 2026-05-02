"""Mode-detection tests."""

from __future__ import annotations

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

    def connect(self, timeout=None):
        return None

    def send_line(self, payload):
        return None

    def recv_line(self, timeout=None):
        return b"{}"

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
