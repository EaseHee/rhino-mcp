"""Geometry validation tool tests."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_validate_brep_closed_box(server_standalone) -> None:
    _mcp, tools = server_standalone
    box = call_tool(
        tools,
        "rhino_box",
        {"corner": {"x": 0, "y": 0, "z": 0}, "size_x": 10.0, "size_y": 10.0, "size_z": 10.0},
    )
    bid = box["summary"]["object_id"]
    res = call_tool(tools, "rhino_validate_brep", {"object_id": bid})
    s = res["summary"]
    assert s["is_valid"] is True
    assert s["is_solid"] is True
    assert s["is_manifold"] is True
    assert s["face_count"] == 6
    assert s["edge_count"] == 12


def test_validate_brep_wrong_kind_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere_pt = call_tool(
        tools,
        "rhino_point",
        {"point": {"x": 0, "y": 0, "z": 0}},
    )
    pid = sphere_pt["summary"]["object_id"]
    with pytest.raises(Exception, match=r".+"):
        call_tool(tools, "rhino_validate_brep", {"object_id": pid})


def test_curve_continuity_line(server_standalone) -> None:
    _mcp, tools = server_standalone
    line = call_tool(
        tools,
        "rhino_line",
        {"start": {"x": 0, "y": 0, "z": 0}, "end": {"x": 5, "y": 0, "z": 0}},
    )
    lid = line["summary"]["object_id"]
    res = call_tool(tools, "rhino_curve_continuity", {"object_id": lid})
    s = res["summary"]
    assert s["is_valid"] is True
    assert s["is_closed"] is False
    assert s["is_planar"] is True
    assert s["span_count"] >= 1


def test_mesh_health_open_mesh(server_standalone) -> None:
    _mcp, tools = server_standalone
    box = call_tool(
        tools,
        "rhino_mesh_box",
        {"corner": {"x": 0, "y": 0, "z": 0}, "size_x": 1.0, "size_y": 1.0, "size_z": 1.0},
    )
    mid = box["summary"]["object_id"]
    res = call_tool(tools, "rhino_report_mesh_health", {"object_id": mid})
    s = res["summary"]
    assert s["is_valid"] is True
    assert s["vertex_count"] > 0
    assert s["face_count"] > 0


def test_naked_edges_unsupported_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    # Bridge-only tool should not be registered in standalone mode.
    assert "rhino_check_naked_edges" not in tools
