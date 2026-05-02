"""Smoke tests for the server registration pipeline."""

from __future__ import annotations

from rhino_mcp.utils.registry import Mode, is_compatible


def test_capability_matrix() -> None:
    assert is_compatible(Mode.BOTH, Mode.STANDALONE) is True
    assert is_compatible(Mode.BOTH, Mode.BRIDGE) is True
    assert is_compatible(Mode.STANDALONE, Mode.STANDALONE) is True
    assert is_compatible(Mode.STANDALONE, Mode.BRIDGE) is False
    assert is_compatible(Mode.BRIDGE, Mode.STANDALONE) is False
    assert is_compatible(Mode.BRIDGE, Mode.BRIDGE) is True


def test_standalone_server_registers_expected_tool_count(server_standalone) -> None:
    _mcp, tools = server_standalone
    # Tools registered in standalone mode: every module marked Mode.BOTH.
    assert len(tools) >= 65, f"expected ≥65 standalone tools, got {len(tools)}"
    # Spot-check core tools are present.
    expected_subset = {
        "rhino_point",
        "rhino_line",
        "rhino_circle",
        "rhino_box",
        "rhino_sphere",
        "rhino_open",
        "rhino_save",
        "rhino_layer_create",
        "rhino_material_create",
        "rhino_move",
        # New: rhinoscript_docs tools must be in standalone
        "rhino_search_rhinoscript_functions",
        "rhino_get_rhinoscript_docs",
    }
    assert expected_subset.issubset(tools.keys())
    # Bridge-only tools must NOT appear in standalone.
    bridge_only = {
        "gh_open_file",
        "rhino_render_viewport",
        "rhino_zoom_extent",
        "rhino_execute_python",
        "rhino_execute_csharp",
        "rhino_undo",
        "rhino_get_selected_objects",
    }
    assert bridge_only.isdisjoint(tools.keys())


def test_bridge_server_registers_more_tools(server_bridge) -> None:
    _mcp, tools = server_bridge
    assert len(tools) >= 120, f"expected ≥120 bridge tools, got {len(tools)}"
    # All bridge-only tools should be present here.
    expected = {
        "rhino_loft",
        "rhino_sweep1",
        "rhino_boolean_union",
        "gh_open_file",
        "gh_set_slider",
        "rhino_render_viewport",
        "rhino_zoom_extent",
        # New tool categories
        "rhino_execute_python",
        "rhino_execute_csharp",
        "rhino_undo",
        "rhino_redo",
        "rhino_batch_modify",
        "rhino_bend",
        "rhino_rebuild_surface",
        "rhino_create_subd",
        "rhino_dup_edge",
        "rhino_get_control_points",
        "rhino_panelize_surface",
        "rhino_get_selected_objects",
    }
    assert expected.issubset(tools.keys())


def test_every_tool_has_description_and_schema(server_standalone) -> None:
    _mcp, tools = server_standalone
    for name, tool in tools.items():
        assert tool.description and tool.description.strip(), f"tool {name} has empty description"
        # FastMCP exposes parameters; an absent schema would mean no input validation.
        assert tool.parameters is not None, f"tool {name} has no input schema"
