"""Solid-tool tests."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_add_box_sphere_cylinder(server_standalone) -> None:
    _mcp, tools = server_standalone
    box = call_tool(
        tools,
        "rhino_box",
        {
            "corner": {"x": 0, "y": 0, "z": 0},
            "size_x": 1,
            "size_y": 2,
            "size_z": 3,
        },
    )
    sphere = call_tool(
        tools, "rhino_sphere", {"center": {"x": 5, "y": 0, "z": 0}, "radius": 2.5}
    )
    cyl = call_tool(
        tools,
        "rhino_cylinder",
        {
            "base_center": {"x": 0, "y": 0, "z": 0},
            "radius": 1.0,
            "height": 5.0,
            "axis": {"x": 0, "y": 0, "z": 1},
        },
    )
    for r in (box, sphere, cyl):
        bb = r["summary"]["bounding_box"]
        assert bb["max"]["x"] > bb["min"]["x"]


def test_cylinder_non_z_axis_rejected_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception):  # noqa: B017
        call_tool(
            tools,
            "rhino_cylinder",
            {
                "base_center": {"x": 0, "y": 0, "z": 0},
                "radius": 1.0,
                "height": 5.0,
                "axis": {"x": 1, "y": 0, "z": 0},
            },
        )


def test_cone_and_torus_emit_meshes(server_standalone) -> None:
    _mcp, tools = server_standalone
    cone = call_tool(
        tools,
        "rhino_cone",
        {
            "base_center": {"x": 0, "y": 0, "z": 0},
            "radius": 2.0,
            "height": 4.0,
        },
    )
    torus = call_tool(
        tools,
        "rhino_torus",
        {
            "center": {"x": 0, "y": 0, "z": 0},
            "major_radius": 5.0,
            "minor_radius": 1.0,
        },
    )
    assert cone["summary"]["object_id"]
    assert torus["summary"]["object_id"]
