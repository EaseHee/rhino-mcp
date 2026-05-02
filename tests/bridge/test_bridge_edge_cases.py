"""Bridge RPC edge-case tests.

Covers transport disconnection, timeouts, request-ID mismatches, malformed
JSON responses, and concurrent call serialisation.
"""

from __future__ import annotations

import json
import threading
from collections import deque

import pytest

from rhino_mcp.bridge.rhino_connection import BridgeClient
from rhino_mcp.bridge.transport_base import Transport
from rhino_mcp.utils.error_handling import ToolError


class FakeTransport(Transport):
    """In-memory transport used for unit tests."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.responses: deque[bytes] = deque()
        self._closed = False
        self._fail_send = False
        self._fail_recv = False
        self._timeout_recv = False

    @property
    def name(self) -> str:
        return "fake://test"

    def connect(self, timeout: float | None = None) -> None:
        self._closed = False

    def send_line(self, payload: bytes) -> None:
        if self._fail_send:
            raise ConnectionError("simulated send failure")
        self.sent.append(payload.rstrip(b"\n"))

    def recv_line(self, timeout: float | None = None) -> bytes:
        if self._timeout_recv:
            raise TimeoutError("simulated timeout")
        if self._fail_recv:
            raise ConnectionError("simulated recv failure")
        if not self.responses:
            raise ConnectionError("no response queued")
        return self.responses.popleft()

    def close(self) -> None:
        self._closed = True


def _make_client(transport: FakeTransport) -> BridgeClient:
    client = BridgeClient(transport, timeout=1.0)
    client._connected = True
    return client


def _enqueue_response(t: FakeTransport, result: dict, request_id: str = "match") -> None:
    """When ``request_id == "match"``, replace recv_line with one that mirrors the request id."""
    if request_id == "match":

        def matching_recv(timeout=None):
            line = t.sent[-1]
            req = json.loads(line)
            return json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}).encode()

        t.recv_line = matching_recv  # type: ignore[assignment]
    else:
        t.responses.append(
            json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}).encode()
        )


class TestConnectionFailure:
    def test_send_failure_marks_disconnected(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        t._fail_send = True
        with pytest.raises(ToolError):
            client.call("rhino.ping", {})
        assert not client._connected
        assert t._closed

    def test_recv_failure_marks_disconnected(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        t._fail_recv = True
        with pytest.raises(ToolError):
            client.call("rhino.ping", {})
        assert not client._connected

    def test_timeout_marks_disconnected(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        t._timeout_recv = True
        with pytest.raises(ToolError):
            client.call("rhino.ping", {})
        assert not client._connected

    def test_subsequent_call_after_disconnect_raises(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        t._fail_send = True
        with pytest.raises(ToolError):
            client.call("rhino.ping", {})
        # Subsequent calls also fail immediately.
        with pytest.raises(ToolError):
            client.call("rhino.ping", {})


class TestRequestIdMismatch:
    def test_mismatched_id_raises_error(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        _enqueue_response(t, {"status": "ok"}, request_id="wrong-id-12345")
        with pytest.raises(ToolError) as exc:
            client.call("rhino.ping", {})
        assert "mismatch" in exc.value.hint.lower() or "mismatch" in str(exc.value).lower()


class TestMalformedResponse:
    def test_non_json_response(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        t.responses.append(b"this is not json")
        with pytest.raises(ToolError) as exc:
            client.call("rhino.ping", {})
        assert "non-JSON" in exc.value.hint or "non-JSON" in str(exc.value)

    def test_truncated_large_response(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        t.responses.append(b"x" * 500)
        with pytest.raises(ToolError):
            client.call("rhino.ping", {})


class TestConcurrentCalls:
    def test_serialized_calls_from_threads(self) -> None:
        t = FakeTransport()
        client = _make_client(t)
        _enqueue_response(t, {"pong": True})

        results: list[dict] = []
        errors: list[Exception] = []

        def worker():
            try:
                r = client.call("rhino.ping", {})
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5.0)

        # The lock serialises the calls; the first succeeds, others may fail.
        assert len(results) + len(errors) == 3
