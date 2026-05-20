"""Verify that BridgeClient._call_once drains rhino.progress notification frames.

The bridge emits ``rhino.heartbeat`` and ``rhino.progress`` JSON-RPC
notification frames (no ``id``) between the request and the eventual
response. The client must skip them while still returning the response
that matches the original request id.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any

import pytest

from rhino_mcp.bridge.rhino_connection import BridgeClient
from rhino_mcp.bridge.transport_base import Transport


@pytest.fixture(autouse=True)
def _propagate_rhino_mcp_logs():
    """Allow caplog (root-attached) to receive rhino_mcp.* records.

    Production sets ``propagate=False`` to keep stdio MCP frames clean;
    tests need propagation to assert on log content.
    """
    parent = logging.getLogger("rhino_mcp")
    previous = parent.propagate
    parent.propagate = True
    yield
    parent.propagate = previous


class _FakeTransport(Transport):
    """In-memory transport whose ``recv_line`` yields pre-staged frames.

    Each ``send_line`` swallows the request; ``recv_line`` returns the
    next staged frame. The test injects the matching response with the
    request id substituted after the send so frame interleaving is
    deterministic.
    """

    def __init__(self, frames: list[dict[str, Any]]):
        self._staged = deque(frames)
        self._sent: list[bytes] = []
        self._closed = False
        self._last_request_id: str | None = None

    def connect(self, timeout: float | None = None) -> None:
        return None

    def send_line(self, payload: bytes) -> None:
        self._sent.append(payload)
        try:
            self._last_request_id = json.loads(payload.decode("utf-8")).get("id")
        except Exception:
            self._last_request_id = None

    def recv_line(self, timeout: float | None = None) -> bytes:
        if not self._staged:
            raise ConnectionError("no more frames staged")
        frame = self._staged.popleft()
        # Substitute the matching id on the response frame so the client
        # accepts it as the response to the last send.
        if "id" in frame and frame.get("id") == "__MATCH__":
            frame = dict(frame)
            frame["id"] = self._last_request_id
        return json.dumps(frame).encode("utf-8")

    def close(self) -> None:
        self._closed = True

    @property
    def name(self) -> str:
        return "fake://"

    def is_alive(self) -> bool:
        return not self._closed


def _build_client(frames: list[dict[str, Any]]) -> BridgeClient:
    transport = _FakeTransport(frames)
    client = BridgeClient(transport, timeout=2.0)
    client._connected = True  # type: ignore[attr-defined]
    return client


def test_progress_frame_drained_then_response(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="rhino_mcp.bridge")
    frames = [
        {
            "jsonrpc": "2.0",
            "method": "rhino.progress",
            "params": {
                "request_id": "abc",
                "progress": 3,
                "total": 10,
                "message": "step 3/10",
            },
        },
        {
            "jsonrpc": "2.0",
            "id": "__MATCH__",
            "result": {"ok": True},
        },
    ]
    client = _build_client(frames)
    result = client.call("rhino.layer.create", {"name": "Walls"})
    assert result == {"ok": True}
    # The drain branch must have logged the progress payload.
    assert any(
        "bridge progress" in rec.getMessage() and "step 3/10" in rec.getMessage()
        for rec in caplog.records
    )


def test_heartbeat_frame_drained_without_progress_log(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="rhino_mcp.bridge")
    frames = [
        {"jsonrpc": "2.0", "method": "rhino.heartbeat"},
        {"jsonrpc": "2.0", "id": "__MATCH__", "result": {"ok": True}},
    ]
    client = _build_client(frames)
    result = client.call("rhino.ping", {})
    assert result == {"ok": True}
    # Heartbeat should NOT surface as a progress log line.
    assert not any("bridge progress" in rec.getMessage() for rec in caplog.records)


def test_progress_log_format_matches_documented_shape(caplog) -> None:
    """Asserts the DEBUG line shape so downstream tooling (grep / dashboards)
    can rely on the documented ``bridge progress: req=<id> progress=<n>/<m> msg=<s>``
    template — this is the visibility surface advertised in v0.6.x release notes.
    """
    caplog.set_level(logging.DEBUG, logger="rhino_mcp.bridge")
    frames = [
        {
            "jsonrpc": "2.0",
            "method": "rhino.progress",
            "params": {
                "request_id": "req-1",
                "progress": 7,
                "total": 50,
                "message": "step 8/50: rhino.layer.create",
            },
        },
        {"jsonrpc": "2.0", "id": "__MATCH__", "result": {"ok": True}},
    ]
    client = _build_client(frames)
    client.call("rhino.batch.execute", {})
    matched = [rec.getMessage() for rec in caplog.records if "bridge progress" in rec.getMessage()]
    assert len(matched) == 1
    line = matched[0]
    assert "req=req-1" in line
    assert "progress=7/50" in line
    assert "step 8/50: rhino.layer.create" in line


def test_mixed_heartbeat_and_progress_frames_drained(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="rhino_mcp.bridge")
    frames = [
        {"jsonrpc": "2.0", "method": "rhino.heartbeat"},
        {
            "jsonrpc": "2.0",
            "method": "rhino.progress",
            "params": {"request_id": "z", "progress": 1, "total": 4, "message": "one"},
        },
        {"jsonrpc": "2.0", "method": "rhino.heartbeat"},
        {
            "jsonrpc": "2.0",
            "method": "rhino.progress",
            "params": {"request_id": "z", "progress": 4, "total": 4, "message": "four"},
        },
        {"jsonrpc": "2.0", "id": "__MATCH__", "result": {"summary": {"ok": True}}},
    ]
    client = _build_client(frames)
    result = client.call("rhino.batch.execute", {})
    assert result == {"summary": {"ok": True}}
    progress_lines = [
        rec.getMessage() for rec in caplog.records if "bridge progress" in rec.getMessage()
    ]
    assert len(progress_lines) == 2
    assert any("one" in m for m in progress_lines)
    assert any("four" in m for m in progress_lines)
