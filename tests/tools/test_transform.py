"""Transform tool tests."""

from __future__ import annotations

from tests.conftest import call_tool


def test_move_in_place_and_copy(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere = call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0})
    sid = sphere["summary"]["object_id"]
    moved = call_tool(
        tools,
        "rhino_move",
        {
            "object_ids": [sid],
            "translation": {"x": 10, "y": 0, "z": 0},
            "make_copy": False,
        },
    )
    assert len(moved["summary"]["object_ids"]) == 1
    copied = call_tool(
        tools,
        "rhino_move",
        {
            "object_ids": moved["summary"]["object_ids"],
            "translation": {"x": 0, "y": 5, "z": 0},
            "make_copy": True,
        },
    )
    assert len(copied["summary"]["object_ids"]) == 1


def test_array_linear_produces_copies(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    pid = p["summary"]["object_id"]
    res = call_tool(
        tools,
        "rhino_array_linear",
        {
            "object_ids": [pid],
            "direction": {"x": 1, "y": 0, "z": 0},
            "spacing": 2.0,
            "count": 5,
        },
    )
    # 5 array slots: 1 original + 4 copies → 4 returned
    assert len(res["summary"]["object_ids"]) == 4


def test_polar_array_full_circle(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = call_tool(tools, "rhino_point", {"point": {"x": 5, "y": 0, "z": 0}})
    res = call_tool(
        tools,
        "rhino_array_polar",
        {
            "object_ids": [p["summary"]["object_id"]],
            "center": {"x": 0, "y": 0, "z": 0},
            "count": 6,
            "total_angle_degrees": 360,
        },
    )
    assert len(res["summary"]["object_ids"]) == 5
