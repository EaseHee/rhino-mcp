"""Grasshopper tool tests using MockBridgeClient.

Verify that bridge-only tools in canvas, components, parameters, and
data_tree modules forward the correct JSON-RPC method names and parameters.
"""

from __future__ import annotations

from typing import Any

import pytest

from rhino_mcp.tools import context as tool_context
from rhino_mcp.utils.registry import Mode


class MockBridgeClient:
    """Records every bridge call and returns a canned result."""

    def __init__(self, default_result: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.default_result = default_result or {"status": "ok"}

    def is_alive(self) -> bool:
        return True

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        return self.default_result


@pytest.fixture
def mock_bridge():
    """Configure the bridge-mode runtime with a MockBridgeClient."""
    client = MockBridgeClient()
    tool_context.set_runtime(Mode.BRIDGE, client)  # type: ignore[arg-type]
    return client


@pytest.fixture
def server_with_mock_bridge(mock_bridge):
    """Return a bridge-mode FastMCP server wired to MockBridgeClient."""
    from rhino_mcp.server import build_server

    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=mock_bridge)  # type: ignore[arg-type]
    mgr = getattr(mcp, "_tool_manager", None)
    tools = mgr._tools if mgr else {}  # type: ignore[attr-defined]
    return tools, mock_bridge


def _call_tool(tools, name, payload):
    import asyncio

    tool = tools[name]
    coro = tool.run({"args": payload})
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


# --- Canvas tools ---


class TestCanvasTools:
    def test_gh_open_file(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_open_file", {"path": "/test/file.gh"})
        assert bridge.calls[-1] == ("gh.canvas.open", {"path": "/test/file.gh"})

    def test_gh_save_file(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_save_file", {"path": "/test/out.gh"})
        assert bridge.calls[-1][0] == "gh.canvas.save"

    def test_gh_new_canvas(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_new_canvas", {"name": "test_doc"})
        assert bridge.calls[-1] == ("gh.canvas.new", {"name": "test_doc"})

    def test_gh_run(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_run", {"new_solution": True})
        assert bridge.calls[-1][0] == "gh.canvas.run"

    def test_gh_bake_to_rhino(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_bake_to_rhino", {"component_ids": ["abc"], "layer": "Bake"})
        method, params = bridge.calls[-1]
        assert method == "gh.canvas.bake"
        assert params["component_ids"] == ["abc"]
        assert params["layer"] == "Bake"


# --- Component tools ---


class TestComponentTools:
    def test_gh_add_component(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_add_component", {"name": "Number Slider", "x": 100, "y": 200})
        method, params = bridge.calls[-1]
        assert method == "gh.component.add"
        assert params["name"] == "Number Slider"

    def test_gh_connect_components(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_connect_components", {
            "from_component": "a",
            "from_output": 0,
            "to_component": "b",
            "to_input": "x",
        })
        assert bridge.calls[-1][0] == "gh.component.connect"

    def test_gh_delete_component(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_delete_component", {"component_id": "abc"})
        assert bridge.calls[-1][0] == "gh.component.delete"

    def test_gh_component_list(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_component_list", {"filter": "Slider"})
        assert bridge.calls[-1] == ("gh.component.list", {"filter": "Slider"})

    def test_gh_cluster_create(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_cluster_create", {"component_ids": ["a", "b"], "name": "MyCluster"})
        assert bridge.calls[-1][0] == "gh.cluster.create"

    def test_gh_cluster_expand(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_cluster_expand", {"cluster_id": "cls1"})
        assert bridge.calls[-1][0] == "gh.cluster.expand"

    def test_gh_plugin_list(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_plugin_list", {})
        assert bridge.calls[-1] == ("gh.plugin.list", {})

    def test_gh_data_tree_get_batch(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(
            tools,
            "gh_data_tree_get_batch",
            {"queries": [{"component_id": "c1", "output": 0}]},
        )
        method, _ = bridge.calls[-1]
        assert method == "gh.data_tree.get_batch"

    def test_gh_data_tree_set_batch(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(
            tools,
            "gh_data_tree_set_batch",
            {
                "assignments": [
                    {
                        "component_id": "c1",
                        "input": 0,
                        "branches": [
                            [
                                {"indices": [0]},
                                [{"type": "number", "value": 1.0}],
                            ]
                        ],
                    }
                ],
                "defer_solve": True,
            },
        )
        method, params = bridge.calls[-1]
        assert method == "gh.data_tree.set_batch"
        assert params["defer_solve"] is True

    def test_gh_components_search(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(
            tools,
            "gh_components_search",
            {"query": "loft", "plugin": "Pufferfish", "category": "Surface", "limit": 25},
        )
        method, params = bridge.calls[-1]
        assert method == "gh.components.search"
        assert params["query"] == "loft"
        assert params["limit"] == 25


# --- Parameter tools ---


class TestParameterTools:
    def test_gh_get_parameter(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_get_parameter", {"component_id": "c1", "output": 0})
        assert bridge.calls[-1][0] == "gh.parameter.get"

    def test_gh_set_parameter(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_set_parameter", {
            "component_id": "c1",
            "input": "x",
            "value": {"type": "number", "value": 42},
        })
        method, params = bridge.calls[-1]
        assert method == "gh.parameter.set"
        assert params["value"]["value"] == 42

    def test_gh_set_slider(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_set_slider", {"component_id": "s1", "value": 3.14})
        assert bridge.calls[-1][0] == "gh.parameter.set_slider"

    def test_gh_set_panel(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_set_panel", {"component_id": "p1", "text": "hello"})
        assert bridge.calls[-1][0] == "gh.parameter.set_panel"

    def test_gh_set_toggle(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_set_toggle", {"component_id": "t1", "value": True})
        assert bridge.calls[-1][0] == "gh.parameter.set_toggle"


# --- DataTree tools ---


class TestDataTreeTools:
    def test_gh_data_tree_get(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_data_tree_get", {"component_id": "d1", "output": 0})
        assert bridge.calls[-1][0] == "gh.data_tree.get"

    def test_gh_data_tree_set(self, server_with_mock_bridge) -> None:
        tools, bridge = server_with_mock_bridge
        _call_tool(tools, "gh_data_tree_set", {
            "component_id": "d1",
            "input": 0,
            "branches": [
                [
                    {"indices": [0, 0]},
                    [
                        {"type": "number", "value": 1.0},
                        {"type": "number", "value": 2.0},
                    ],
                ]
            ],
        })
        assert bridge.calls[-1][0] == "gh.data_tree.set"
