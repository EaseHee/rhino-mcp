"""rhino_object_select filter coverage (standalone mode)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rhino_mcp.utils.error_handling import ToolError
from tests.conftest import call_tool


def _add_point(tools, x: float, *, name: str | None = None, layer: str | None = None) -> str:
    args: dict = {"point": {"x": x, "y": 0, "z": 0}}
    if name is not None:
        args["name"] = name
    if layer is not None:
        args["layer"] = layer
    res = call_tool(tools, "rhino_point", args)
    return res["summary"]["object_id"]


def test_select_by_name_pattern(server_standalone) -> None:
    _mcp, tools = server_standalone
    a = _add_point(tools, 0.0, name="Wall_A")
    _ = _add_point(tools, 1.0, name="Wall_B")
    _other = _add_point(tools, 2.0, name="Floor_1")

    res = call_tool(tools, "rhino_object_select", {"name_pattern": "Wall_*"})
    matched = set(res["summary"]["object_ids"])
    assert a in matched
    assert _other not in matched
    assert res["summary"]["count"] == 2


def test_select_by_layer(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_layer_create", {"name": "Walls"})
    call_tool(tools, "rhino_layer_create", {"name": "Floors"})
    p1 = _add_point(tools, 0.0, layer="Walls")
    p2 = _add_point(tools, 1.0, layer="Floors")

    res = call_tool(tools, "rhino_object_select", {"layer": "Walls"})
    assert p1 in res["summary"]["object_ids"]
    assert p2 not in res["summary"]["object_ids"]


def test_select_by_object_ids_validates_existence(server_standalone) -> None:
    _mcp, tools = server_standalone
    p = _add_point(tools, 0.0)
    res = call_tool(tools, "rhino_object_select", {"object_ids": [p]})
    assert res["summary"]["object_ids"] == [p]

    with pytest.raises((ToolError, Exception)) as exc:
        call_tool(
            tools,
            "rhino_object_select",
            {"object_ids": ["00000000-0000-0000-0000-000000000000"]},
        )
    assert "00000000" in str(exc.value)


def test_select_combines_filters_with_and(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_layer_create", {"name": "Walls"})
    call_tool(tools, "rhino_layer_create", {"name": "Floors"})
    a = _add_point(tools, 0.0, name="Wall_A", layer="Walls")
    b = _add_point(tools, 1.0, name="Wall_B", layer="Floors")  # right name, wrong layer
    c = _add_point(tools, 2.0, name="Floor_1", layer="Walls")  # right layer, wrong name

    res = call_tool(
        tools,
        "rhino_object_select",
        {"name_pattern": "Wall_*", "layer": "Walls"},
    )
    matched = res["summary"]["object_ids"]
    assert a in matched
    assert b not in matched
    assert c not in matched


def test_select_color_validation_rejects_out_of_range() -> None:
    from rhino_mcp.tools.layers import _ObjectSelectIn

    with pytest.raises(ValidationError):
        _ObjectSelectIn(color=(300, 0, 0))
