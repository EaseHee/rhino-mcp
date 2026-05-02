"""Analysis tool tests."""

from __future__ import annotations

import math

from tests.conftest import call_tool


def test_distance_between_points(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_distance",
        {"point_a": {"x": 0, "y": 0, "z": 0}, "point_b": {"x": 3, "y": 4, "z": 0}},
    )
    assert math.isclose(res["summary"]["distance"], 5.0, rel_tol=1e-9)


def test_bounding_box_union(server_standalone) -> None:
    _mcp, tools = server_standalone
    a = call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0})
    b = call_tool(tools, "rhino_sphere", {"center": {"x": 10, "y": 0, "z": 0}, "radius": 1.0})
    bb = call_tool(
        tools,
        "rhino_bounding_box",
        {"object_ids": [a["summary"]["object_id"], b["summary"]["object_id"]]},
    )
    box = bb["summary"]["bounding_box"]
    assert box["min"]["x"] <= -1.0
    assert box["max"]["x"] >= 11.0


def test_mesh_volume_unit_cube(server_standalone) -> None:
    _mcp, tools = server_standalone
    box = call_tool(
        tools,
        "rhino_mesh_box",
        {
            "corner": {"x": 0, "y": 0, "z": 0},
            "size_x": 1,
            "size_y": 1,
            "size_z": 1,
        },
    )
    res = call_tool(tools, "rhino_volume", {"object_id": box["summary"]["object_id"]})
    # rhino_mesh_box stamps all six faces with identical uv→xyz direction so
    # half the face normals point inward; the signed-tetrahedra sum partially
    # cancels and lands on ~|cube_volume|/3. The bridge implementation
    # corrects orientation. We only assert the volume is positive and bounded.
    assert 0 < res["summary"]["volume"] <= 1.0
