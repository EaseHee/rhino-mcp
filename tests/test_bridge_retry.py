"""Dual-mode tools re-detect the bridge when their standalone path refuses an operation."""

from __future__ import annotations

from typing import Any

import pytest

from rhino_mcp.bridge.rhino_connection import BridgeClient
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode
from tests.conftest import call_tool


class _FakeBridge:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def is_alive(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def call(self, method: str, params: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(method)
        return {"summary": {"method": method}, "text": "ok"}


@pytest.fixture
def detection(monkeypatch: pytest.MonkeyPatch) -> tuple[list[float], list[Any]]:
    """Stub BridgeClient.auto; append a client to ``queue`` to make the next detection succeed."""
    calls: list[float] = []
    queue: list[Any] = []

    def _auto(cls: Any, timeout: float = 5.0) -> Any:
        calls.append(timeout)
        return queue.pop(0) if queue else None

    monkeypatch.setattr(BridgeClient, "auto", classmethod(_auto))
    return calls, queue


@pytest.fixture
def auto_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest forces standalone for the suite; promotion needs auto mode.
    monkeypatch.delenv("RHINO_MCP_FORCE_MODE", raising=False)


def _export_args(tmp_path: Any) -> dict[str, Any]:
    return {"path": str(tmp_path / "out.stp")}


def test_sync_tool_retries_on_bridge_after_promotion(server_standalone, detection, auto_mode, tmp_path) -> None:
    calls, queue = detection
    _mcp, tools = server_standalone
    bridge = _FakeBridge()
    queue.append(bridge)

    result = call_tool(tools, "rhino_export_step", _export_args(tmp_path))

    assert result["summary"]["method"] == "rhino.io.export_step"
    assert bridge.calls == ["rhino.io.export_step"]
    assert len(calls) == 1
    assert runtime().mode is Mode.BRIDGE


def test_async_tool_retries_on_bridge_after_promotion(server_standalone, detection, auto_mode, tmp_path) -> None:
    calls, queue = detection
    _mcp, tools = server_standalone
    bridge = _FakeBridge()
    queue.append(bridge)

    result = call_tool(tools, "rhino_export_ifc", {"path": str(tmp_path / "out.ifc")})

    assert bridge.calls == ["rhino.bim.export_ifc"], result
    assert len(calls) == 1


def test_unreachable_bridge_keeps_original_error(server_standalone, detection, auto_mode, tmp_path) -> None:
    calls, _queue = detection
    _mcp, tools = server_standalone

    with pytest.raises(Exception, match="requires Rhino bridge mode"):
        call_tool(tools, "rhino_export_step", _export_args(tmp_path))
    assert len(calls) == 1
    assert runtime().mode is Mode.STANDALONE


def test_forced_standalone_never_redetects(server_standalone, detection, monkeypatch, tmp_path) -> None:
    calls, queue = detection
    _mcp, tools = server_standalone
    queue.append(_FakeBridge())
    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")

    with pytest.raises(Exception, match="requires Rhino bridge mode"):
        call_tool(tools, "rhino_export_step", _export_args(tmp_path))
    assert calls == []


def test_redetection_respects_cooldown(server_standalone, detection, auto_mode, tmp_path) -> None:
    calls, _queue = detection
    _mcp, tools = server_standalone
    for _ in range(3):
        with pytest.raises(Exception, match="requires Rhino bridge mode"):
            call_tool(tools, "rhino_export_step", _export_args(tmp_path))
    # One detection; the next two calls fall inside RHINO_MCP_REDETECT_COOLDOWN.
    assert len(calls) == 1


def test_other_errors_do_not_redetect(server_standalone, detection, auto_mode) -> None:
    calls, queue = detection
    _mcp, tools = server_standalone
    queue.append(_FakeBridge())

    with pytest.raises(Exception, match=r"not found|Not found|not_found"):
        call_tool(tools, "rhino_object_info", {"object_id": "00000000-0000-0000-0000-000000000001"})
    assert calls == []


def test_bridge_mode_refusal_is_not_retried(server_bridge, detection, auto_mode, tmp_path) -> None:
    # rhino_export_draco raises an `unsupported` error in bridge mode; retrying cannot help.
    calls, _queue = detection
    _mcp, tools = server_bridge

    with pytest.raises(Exception, match="standalone rhino3dm document only"):
        call_tool(tools, "rhino_export_draco", {"path": str(tmp_path / "m.drc")})
    assert calls == []
