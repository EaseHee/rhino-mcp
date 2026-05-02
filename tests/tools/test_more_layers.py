"""Additional layer/group/material tests."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_layer_delete(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_layer_create", {"name": "Tmp"})
    res = call_tool(tools, "rhino_layer_delete", {"name": "Tmp"})
    assert "deleted" in res["text"]


def test_object_move_to_layer(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    res = call_tool(
        tools,
        "rhino_object_move_to_layer",
        {"object_ids": [p["summary"]["object_id"]], "layer": "Wires"},
    )
    assert res["summary"]["layer"] == "Wires"


def test_object_select(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    res = call_tool(tools, "rhino_object_select", {"object_ids": [p["summary"]["object_id"]]})
    assert "Selected" in res["text"]


def test_group_objects(server_standalone) -> None:
    _mcp, tools = server_standalone
    a = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    b = call_tool(tools, "rhino_point", {"point": {"x": 1, "y": 0, "z": 0}})
    res = call_tool(
        tools,
        "rhino_group",
        {
            "object_ids": [a["summary"]["object_id"], b["summary"]["object_id"]],
            "name": "MyGroup",
        },
    )
    assert res["summary"]["name"] == "MyGroup"


def test_material_assign_unknown_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    with pytest.raises(Exception):  # noqa: B017
        call_tool(
            tools,
            "rhino_material_assign",
            {"material_name": "ghost", "object_ids": [p["summary"]["object_id"]]},
        )


def test_layer_set_color_unknown_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception):  # noqa: B017
        call_tool(
            tools,
            "rhino_layer_set_color",
            {"name": "ghost", "color": {"r": 1, "g": 2, "b": 3}},
        )
