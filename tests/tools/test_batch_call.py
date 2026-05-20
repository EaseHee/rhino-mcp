"""Tests for rhino_batch_call tool (tools/batch_call.py)."""

from __future__ import annotations

from typing import Any

import pytest

from rhino_mcp.tools import context as tool_context
from rhino_mcp.utils.registry import Mode
from tests.conftest import call_tool


class _MockBridgeClient:
    def __init__(self, default_result: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.default_result = default_result or {
            "summary": {"total": 0, "ok": 0, "failed": 0, "on_error": "stop"},
            "results": [],
        }

    def is_alive(self) -> bool:
        return True

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        return self.default_result


@pytest.fixture
def bridge_server():
    from rhino_mcp.server import build_server

    client = _MockBridgeClient(
        default_result={
            "summary": {"total": 2, "ok": 2, "failed": 0, "on_error": "stop"},
            "results": [
                {"index": 0, "method": "rhino.layer.create", "status": "ok", "result": {}},
                {"index": 1, "method": "rhino.layer.create", "status": "ok", "result": {}},
            ],
        }
    )
    tool_context.set_runtime(Mode.BRIDGE, client)  # type: ignore[arg-type]
    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=client)  # type: ignore[arg-type]
    mgr = getattr(mcp, "_tool_manager", None)
    tools = mgr._tools if mgr else {}  # type: ignore[attr-defined]
    return tools, client


def test_batch_call_forwards_steps_to_bridge(bridge_server):
    tools, client = bridge_server
    payload = {
        "steps": [
            {"method": "rhino.layer.create", "params": {"name": "Walls"}},
            {"method": "rhino.layer.create", "params": {"name": "Slabs"}},
        ],
        "on_error": "stop",
    }
    result = call_tool(tools, "rhino_batch_call", payload)
    structured = result[1] if isinstance(result, tuple) else result

    assert client.calls == [
        (
            "rhino.batch.execute",
            {
                "steps": [
                    {"method": "rhino.layer.create", "params": {"name": "Walls"}},
                    {"method": "rhino.layer.create", "params": {"name": "Slabs"}},
                ],
                "on_error": "stop",
            },
        )
    ]
    assert structured["summary"]["ok"] == 2
    assert "Batch executed: 2/2 ok" in structured["text"]


def test_batch_call_continue_on_error_forwarded(bridge_server):
    tools, client = bridge_server
    call_tool(
        tools,
        "rhino_batch_call",
        {
            "steps": [{"method": "rhino.layer.create", "params": {}}],
            "on_error": "continue",
        },
    )
    assert client.calls[-1][1]["on_error"] == "continue"


def test_batch_call_rejects_unknown_method_prefix(bridge_server):
    tools, _ = bridge_server
    with pytest.raises(Exception, match=r"(?i)invalid parameter.*steps\[0\]\.method"):
        call_tool(
            tools,
            "rhino_batch_call",
            {"steps": [{"method": "evil.exec", "params": {}}]},
        )


def test_batch_call_rejects_oversized_batch(bridge_server):
    tools, _ = bridge_server
    payload = {
        "steps": [{"method": "rhino.layer.create", "params": {}} for _ in range(257)],
    }
    with pytest.raises(Exception, match=r"(?i)at most 256|max_length|too long"):
        call_tool(tools, "rhino_batch_call", payload)


def test_batch_call_unsupported_in_standalone(server_standalone):
    _mcp, tools = server_standalone
    payload = {
        "steps": [{"method": "rhino.layer.create", "params": {}}],
    }
    with pytest.raises(Exception, match=r"(?i)bridge|standalone"):
        call_tool(tools, "rhino_batch_call", payload)
