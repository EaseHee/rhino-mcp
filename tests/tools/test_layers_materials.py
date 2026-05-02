"""Layer + material tool tests."""

from __future__ import annotations

from tests.conftest import call_tool


def test_layer_create_and_color(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_layer_create",
        {"name": "Walls", "color": {"r": 255, "g": 0, "b": 0}, "visible": True},
    )
    assert res["summary"]["index"] >= 0
    call_tool(
        tools,
        "rhino_layer_set_color",
        {"name": "Walls", "color": {"r": 0, "g": 255, "b": 0}},
    )


def test_material_create_and_assign(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere = call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0})
    call_tool(
        tools,
        "rhino_material_create",
        {"name": "Glass", "diffuse": {"r": 200, "g": 220, "b": 255}, "transparency": 0.7},
    )
    res = call_tool(
        tools,
        "rhino_material_assign",
        {
            "material_name": "Glass",
            "object_ids": [sphere["summary"]["object_id"]],
        },
    )
    assert "Glass" in res["text"]


def test_object_delete(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    res = call_tool(tools, "rhino_object_delete", {"object_ids": [p["summary"]["object_id"]]})
    assert res["summary"]["deleted"] == [p["summary"]["object_id"]]
