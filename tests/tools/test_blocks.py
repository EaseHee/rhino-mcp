"""Block / instance tests (define, insert, list, bridge gating)."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def _make_sphere(tools) -> str:
    res = call_tool(
        tools,
        "rhino_sphere",
        {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0},
    )
    return res["summary"]["object_id"]


def test_block_define_and_list(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    define = call_tool(
        tools,
        "rhino_block_define",
        {
            "object_ids": [sid],
            "base_point": {"x": 0, "y": 0, "z": 0},
            "name": "Sphere_Block",
            "description": "demo",
        },
    )
    assert define["summary"]["object_count"] == 1
    listing = call_tool(tools, "rhino_block_list", {})
    names = [d["name"] for d in listing["summary"]["definitions"]]
    assert "Sphere_Block" in names


def test_block_define_duplicate_name_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    call_tool(
        tools,
        "rhino_block_define",
        {
            "object_ids": [sid],
            "base_point": {"x": 0, "y": 0, "z": 0},
            "name": "Dup",
        },
    )
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_block_define",
            {
                "object_ids": [sid],
                "base_point": {"x": 0, "y": 0, "z": 0},
                "name": "Dup",
            },
        )


def test_block_insert_unknown_definition(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_block_insert",
            {
                "name": "Missing_Block",
                "insertion_point": {"x": 5, "y": 5, "z": 0},
            },
        )


def test_block_explode_unsupported_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_block_explode",
            {"instance_id": "00000000-0000-0000-0000-000000000000"},
        )


def test_block_redefine_unsupported_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_block_redefine",
            {"name": "Anything", "object_ids": ["00000000-0000-0000-0000-000000000000"]},
        )
