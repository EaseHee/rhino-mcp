"""Bridge ``rhino.progress`` frames reach an MCP client as progress notifications.

A fake transport replays progress frames ahead of the response. The response
is held back until the client has observed the first notification, so the
test only passes if progress is delivered *while* the bridge call is still
in flight (i.e. the event loop is not blocked by the tool).
"""

from __future__ import annotations

import itertools
import json
import threading
from collections import deque
from typing import Any

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from rhino_mcp.bridge.rhino_connection import BridgeClient
from rhino_mcp.bridge.transport_base import Transport
from rhino_mcp.tools import context as tool_context
from rhino_mcp.utils.registry import Mode

_MATCH = "__MATCH__"


class _ProgressTransport(Transport):
    """Replays staged frames; ``__MATCH__`` ids are bound to the last request id."""

    def __init__(self, frames: list[dict[str, Any]], gate: threading.Event | None = None) -> None:
        self._staged = deque(frames)
        self._gate = gate
        self.gate_opened: bool | None = None
        self._last_request_id: str | None = None
        self._closed = False

    def connect(self, timeout: float | None = None) -> None:
        return None

    def send_line(self, payload: bytes) -> None:
        self._last_request_id = json.loads(payload.decode("utf-8")).get("id")

    def recv_line(self, timeout: float | None = None) -> bytes:
        if not self._staged:
            raise ConnectionError("no more frames staged")
        frame = json.loads(json.dumps(self._staged.popleft()))
        if frame.get("id") == _MATCH:
            # Hold the response until the client saw progress (or give up).
            if self._gate is not None:
                self.gate_opened = self._gate.wait(timeout=5.0)
            frame["id"] = self._last_request_id
        params = frame.get("params")
        if isinstance(params, dict) and params.get("request_id") == _MATCH:
            params["request_id"] = self._last_request_id
        return json.dumps(frame).encode("utf-8")

    def close(self) -> None:
        self._closed = True

    @property
    def name(self) -> str:
        return "fake-progress://"

    def is_alive(self) -> bool:
        return not self._closed


def _progress(progress: float | None, total: float | None, message: str, req: str = _MATCH) -> dict:
    params: dict[str, Any] = {"request_id": req, "message": message}
    if progress is not None:
        params["progress"] = progress
    if total is not None:
        params["total"] = total
    return {"jsonrpc": "2.0", "method": "rhino.progress", "params": params}


def _client(frames: list[dict[str, Any]], gate: threading.Event | None = None) -> tuple[BridgeClient, _ProgressTransport]:
    transport = _ProgressTransport(frames, gate)
    client = BridgeClient(transport, timeout=10.0)
    client._connected = True
    return client, transport


_BATCH_RESULT = {
    "summary": {"total": 2, "ok": 2, "failed": 0, "on_error": "stop"},
    "results": [],
}


def test_on_progress_filters_foreign_request_ids() -> None:
    frames = [
        {"jsonrpc": "2.0", "method": "rhino.heartbeat", "params": {}},
        _progress(0, 3, "start"),
        _progress(9, 9, "other call", req="someone-else"),
        _progress(None, None, "message only"),
        _progress("2", "3", "string numbers"),
        {"jsonrpc": "2.0", "id": _MATCH, "result": {"ok": True}},
    ]
    client, _ = _client(frames)
    seen: list[tuple[Any, Any, Any]] = []
    result = client.call("rhino.x.y", {}, on_progress=lambda p, t, m: seen.append((p, t, m)))
    assert result == {"ok": True}
    assert seen == [
        (0.0, 3.0, "start"),
        (None, None, "message only"),
        (2.0, 3.0, "string numbers"),
    ]


def test_on_progress_callback_errors_do_not_break_call() -> None:
    frames = [_progress(1, 2, "x"), {"jsonrpc": "2.0", "id": _MATCH, "result": {"ok": 1}}]
    client, _ = _client(frames)

    def boom(*_: Any) -> None:
        raise RuntimeError("callback failure")

    assert client.call("rhino.x.y", {}, on_progress=boom) == {"ok": 1}


@pytest.fixture
def _restore_runtime():
    yield
    tool_context.set_runtime(Mode.STANDALONE, None)


async def _call_with_progress(client: BridgeClient, tool: str, arguments: dict[str, Any], gate: threading.Event):
    from rhino_mcp.server import build_server

    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=client)
    received: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress: float, total: float | None, message: str | None) -> None:
        received.append((progress, total, message))
        gate.set()

    async with create_connected_server_and_client_session(mcp) as session:
        listed = await session.list_tools()
        schemas = {t.name: t.inputSchema for t in listed.tools}
        with anyio.fail_after(15):
            result = await session.call_tool(tool, {"args": arguments}, progress_callback=on_progress)
    return result, received, schemas


def test_batch_call_streams_progress_to_client(_restore_runtime) -> None:
    gate = threading.Event()
    frames = [
        _progress(0, 2, "step 1/2: rhino.layer.create"),
        _progress(1, 2, "step 2/2: rhino.layer.create"),
        {"jsonrpc": "2.0", "id": _MATCH, "result": _BATCH_RESULT},
    ]
    client, transport = _client(frames, gate)
    args = {
        "steps": [
            {"method": "rhino.layer.create", "params": {"name": "A"}},
            {"method": "rhino.layer.create", "params": {"name": "B"}},
        ]
    }
    result, received, schemas = anyio.run(_call_with_progress, client, "rhino_batch_call", args, gate)

    assert result.isError is False, result.content
    assert transport.gate_opened is True, "progress was not delivered while the call was in flight"
    assert received == [
        (0.0, 2.0, "step 1/2: rhino.layer.create"),
        (1.0, 2.0, "step 2/2: rhino.layer.create"),
    ]
    # The injected Context must not leak into the tool's input schema.
    assert list(schemas["rhino_batch_call"]["properties"]) == ["args"]
    for name in ("rhino_export_ifc", "rhino_import_ifc", "rhino_make2d", "rhino_render_queue_submit"):
        assert list(schemas[name]["properties"]) == ["args"], name


def test_make2d_message_only_frame_reuses_last_progress(_restore_runtime) -> None:
    gate = threading.Event()
    frames = [
        _progress(0, 2, "Make2D: selecting 2 object(s)"),
        _progress(2, 2, "Make2D: selected 2/2"),
        _progress(None, None, "Make2D: running command (no intermediate progress)"),
        {"jsonrpc": "2.0", "id": _MATCH, "result": {"curve_ids": []}},
    ]
    client, transport = _client(frames, gate)
    args = {"object_ids": ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]}
    result, received, _ = anyio.run(_call_with_progress, client, "rhino_make2d", args, gate)

    assert result.isError is False, result.content
    assert transport.gate_opened is True
    values = [r[0] for r in received]
    assert values[:2] == [0.0, 2.0]
    # MCP requires strictly increasing progress, even for message-only frames.
    assert all(b > a for a, b in itertools.pairwise(values)), values
    assert values[2] < 2.0 + 1e-9
    assert all(r[1] is None or r[1] >= r[0] for r in received), received
    assert received[-1][2] == "Make2D: running command (no intermediate progress)"
