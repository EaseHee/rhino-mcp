"""Bridge JSON-RPC protocol tests against an in-memory transport."""

from __future__ import annotations

import json
from collections import deque

import pytest

from rhino_mcp.bridge.rhino_connection import BridgeClient
from rhino_mcp.bridge.transport_base import Transport
from rhino_mcp.utils.error_handling import ToolError


class FakeTransport(Transport):
    """Loopback transport that lets the test enqueue canned responses."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.responses: deque[bytes] = deque()
        self._closed = False

    @property
    def name(self) -> str:
        return "fake://memory"

    def connect(self, timeout: float | None = None) -> None:
        return None

    def send_line(self, payload: bytes) -> None:
        self.sent.append(payload.rstrip(b"\n"))

    def recv_line(self, timeout: float | None = None) -> bytes:
        if not self.responses:
            raise AssertionError("no canned response queued")
        return self.responses.popleft()

    def close(self) -> None:
        self._closed = True


def _enqueue_result(t: FakeTransport, request_id_supplier, result) -> None:
    """Build a JSON-RPC response that mirrors whatever id the next request uses."""

    def respond(line_bytes: bytes) -> None:
        request = json.loads(line_bytes)
        t.responses.append(
            json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode("utf-8")
        )

    request_id_supplier.append(respond)


def test_call_round_trips_request_and_result() -> None:
    t = FakeTransport()
    client = BridgeClient(t, timeout=1.0)
    client._connected = True  # simulate post-connect state

    # Pre-canned response that echoes the request id.
    def fake_recv(timeout=None):
        line = t.sent[-1]
        request = json.loads(line)
        return json.dumps(
            {"jsonrpc": "2.0", "id": request["id"], "result": {"object_id": "abc"}}
        ).encode("utf-8")

    t.recv_line = fake_recv  # type: ignore[assignment]

    result = client.call("rhino.solid.sphere", {"radius": 5.0})
    assert result == {"object_id": "abc"}
    sent = json.loads(t.sent[0])
    assert sent["method"] == "rhino.solid.sphere"
    assert sent["params"] == {"radius": 5.0}
    assert sent["jsonrpc"] == "2.0"


def test_call_raises_tool_error_on_rpc_error() -> None:
    t = FakeTransport()
    client = BridgeClient(t, timeout=1.0)
    client._connected = True

    def fake_recv(timeout=None):
        line = t.sent[-1]
        request = json.loads(line)
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {
                    "code": -32000,
                    "message": "object not found",
                    "data": {"hint": "Pass a valid GUID."},
                },
            }
        ).encode("utf-8")

    t.recv_line = fake_recv  # type: ignore[assignment]

    with pytest.raises(ToolError) as exc:
        client.call("rhino.object.move_to_layer", {"object_ids": ["bad"], "layer": "x"})
    assert "object not found" in exc.value.message
    assert exc.value.hint
