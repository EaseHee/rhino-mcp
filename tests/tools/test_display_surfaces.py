"""Display, Surface, and Mesh tool tests."""

from __future__ import annotations

from typing import Any

import pytest

from rhino_mcp.tools import context as tool_context
from rhino_mcp.utils.registry import Mode


class MockBridgeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        return {"status": "ok"}


@pytest.fixture
def bridge_tools():
    client = MockBridgeClient()
    tool_context.set_runtime(Mode.BRIDGE, client)  # type: ignore[arg-type]
    from rhino_mcp.server import build_server

    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=client)  # type: ignore[arg-type]
    mgr = getattr(mcp, "_tool_manager", None)
    tools = mgr._tools if mgr else {}  # type: ignore[attr-defined]
    return tools, client


def _call(tools, name, payload):
    import asyncio

    tool = tools[name]
    coro = tool.run({"args": payload})
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


# --- Display tools ---


class TestDisplayTools:
    def test_view_set(self, bridge_tools) -> None:
        tools, client = bridge_tools
        _call(tools, "rhino_view_set", {"name": "Front"})
        assert client.calls[-1][0] == "rhino.display.view_set"

    def test_zoom_extent(self, bridge_tools) -> None:
        tools, client = bridge_tools
        _call(tools, "rhino_zoom_extent", {})
        assert client.calls[-1][0] == "rhino.display.zoom_extent"

    def test_named_view_save(self, bridge_tools) -> None:
        tools, client = bridge_tools
        _call(tools, "rhino_named_view_save", {"name": "MyView"})
        assert client.calls[-1][0] == "rhino.display.named_view_save"

    def test_display_mode_set(self, bridge_tools) -> None:
        tools, client = bridge_tools
        _call(tools, "rhino_display_mode_set", {"mode": "Shaded"})
        assert client.calls[-1][0] == "rhino.display.mode_set"

    def test_turntable(self, bridge_tools) -> None:
        tools, client = bridge_tools
        _call(tools, "rhino_turntable", {"output_path": "/tmp/out.gif", "frames": 60})
        method, params = client.calls[-1]
        assert method == "rhino.display.turntable"
        assert params["frames"] == 60


# --- Surface tools (standalone fallbacks) ---


class TestSurfaceStandalone:
    def test_plane_surface_standalone(self, server_standalone) -> None:
        """rhino_plane_surface: standalone NurbsSurface fallback."""
        _mcp, tools = server_standalone
        result = _call(
            tools,
            "rhino_plane_surface",
            {
                "plane": {"origin": {"x": 0, "y": 0, "z": 0}},
                "width": 10.0,
                "height": 5.0,
            },
        )
        assert result["summary"]["kind"] == "PlaneSurface"
        assert result["summary"]["object_id"]

    def test_extrude_standalone(self, server_standalone) -> None:
        """rhino_extrude: standalone Extrusion fallback."""
        from tests.conftest import call_tool

        _mcp, tools = server_standalone
        # Create a circle to extrude.
        circle = call_tool(tools, "rhino_circle", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 3.0})
        profile_id = circle["summary"]["object_id"]
        result = _call(
            tools,
            "rhino_extrude",
            {
                "profile_id": profile_id,
                "direction": {"x": 0.0, "y": 0.0, "z": 1.0},
                "distance": 10.0,
                "capped": True,
            },
        )
        assert result["summary"]["kind"] == "Extrusion"

    def test_extrude_not_found_raises(self, server_standalone) -> None:
        """rhino_extrude: missing profile_id raises ToolError."""
        _mcp, tools = server_standalone
        with pytest.raises(Exception):  # noqa: B017
            _call(
                tools,
                "rhino_extrude",
                {
                    "profile_id": "00000000-0000-0000-0000-000000000000",
                    "direction": {"x": 0.0, "y": 0.0, "z": 1.0},
                    "distance": 5.0,
                },
            )

    def test_surface_tools_registered_in_bridge_mode(self, bridge_tools) -> None:
        tools, _ = bridge_tools
        surface_tool_names = [k for k in tools if "surface" in k.lower() or "loft" in k.lower() or "sweep" in k.lower()]
        assert len(surface_tool_names) > 0


# --- Mesh tools (standalone) ---


class TestMeshStandalone:
    def test_mesh_box_standalone(self) -> None:
        from rhino_mcp.server import build_server

        tool_context.set_runtime(Mode.STANDALONE, None)
        mcp, _ = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
        mgr = getattr(mcp, "_tool_manager", None)
        tools = mgr._tools if mgr else {}  # type: ignore[attr-defined]
        if "rhino_mesh_box" in tools:
            result = _call(tools, "rhino_mesh_box", {
                "corner": {"x": 0, "y": 0, "z": 0},
                "size_x": 10, "size_y": 10, "size_z": 10,
            })
            assert "summary" in result or "status" in result
