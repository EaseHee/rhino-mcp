"""Additional transform tests for rotate/scale/mirror/orient/rectangular array/bbox."""

from __future__ import annotations

from tests.conftest import call_tool


def test_rotate_and_scale_and_mirror(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere = call_tool(tools, "rhino_sphere", {"center": {"x": 5, "y": 0, "z": 0}, "radius": 1.0})
    sid = sphere["summary"]["object_id"]
    rotated = call_tool(
        tools,
        "rhino_rotate",
        {
            "object_ids": [sid],
            "center": {"x": 0, "y": 0, "z": 0},
            "axis": {"x": 0, "y": 0, "z": 1},
            "angle_degrees": 90,
            "make_copy": True,
        },
    )
    scaled = call_tool(
        tools,
        "rhino_scale",
        {
            "object_ids": [sid],
            "center": {"x": 0, "y": 0, "z": 0},
            "factor_x": 2.0,
            "factor_y": 2.0,
            "factor_z": 2.0,
            "make_copy": True,
        },
    )
    mirrored = call_tool(
        tools,
        "rhino_mirror",
        {
            "object_ids": [sid],
            "plane": {
                "origin": {"x": 0, "y": 0, "z": 0},
                "x_axis": {"x": 0, "y": 1, "z": 0},
                "y_axis": {"x": 0, "y": 0, "z": 1},
            },
            "make_copy": True,
        },
    )
    for r in (rotated, scaled, mirrored):
        assert len(r["summary"]["object_ids"]) == 1


def test_array_rectangular(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    res = call_tool(
        tools,
        "rhino_array_rectangular",
        {
            "object_ids": [p["summary"]["object_id"]],
            "count_x": 3,
            "count_y": 2,
            "count_z": 1,
            "spacing_x": 1.0,
            "spacing_y": 2.0,
        },
    )
    # 3x2x1 = 6 cells, minus the seed (0,0,0) = 5 copies.
    assert len(res["summary"]["object_ids"]) == 5


def test_orient(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere = call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0})
    res = call_tool(
        tools,
        "rhino_orient",
        {
            "object_ids": [sphere["summary"]["object_id"]],
            "from_plane": {
                "origin": {"x": 0, "y": 0, "z": 0},
                "x_axis": {"x": 1, "y": 0, "z": 0},
                "y_axis": {"x": 0, "y": 1, "z": 0},
            },
            "to_plane": {
                "origin": {"x": 5, "y": 5, "z": 0},
                "x_axis": {"x": 1, "y": 0, "z": 0},
                "y_axis": {"x": 0, "y": 1, "z": 0},
            },
            "make_copy": True,
        },
    )
    assert len(res["summary"]["object_ids"]) == 1


def test_selection_bbox(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0})
    call_tool(tools, "rhino_sphere", {"center": {"x": 10, "y": 0, "z": 0}, "radius": 1.0})
    res = call_tool(tools, "rhino_selection_bbox", {})
    assert res["summary"]["bounding_box"]["max"]["x"] >= 11.0
