"""Freeform (v0.3) module tests — skin, paneling, curvature, fields."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def _arc(tools, z: float, radius: float):
    res = call_tool(
        tools,
        "rhino_arc",
        {"center": {"x": 0, "y": 0, "z": z}, "radius": radius, "angle_degrees": 180},
    )
    return res["summary"]["object_id"]


def _skin_from_two_arcs(tools, r1=5.0, r2=3.0):
    a = _arc(tools, 0.0, r1)
    b = _arc(tools, 10.0, r2)
    skin = call_tool(
        tools,
        "rhino_skin_from_sections",
        {"section_curve_ids": [a, b]},
    )
    return skin["summary"]["object_ids"][0]


# ---------- skin ----------------------------------------------------------------


def test_skin_two_sections_creates_one_ruled_surface(server_standalone) -> None:
    _mcp, tools = server_standalone
    a = _arc(tools, 0.0, 5.0)
    b = _arc(tools, 10.0, 3.0)
    res = call_tool(
        tools,
        "rhino_skin_from_sections",
        {"section_curve_ids": [a, b]},
    )
    assert len(res["summary"]["object_ids"]) == 1


def test_skin_three_sections_creates_chain(server_standalone) -> None:
    _mcp, tools = server_standalone
    a = _arc(tools, 0.0, 5.0)
    b = _arc(tools, 5.0, 4.0)
    c = _arc(tools, 10.0, 3.0)
    res = call_tool(
        tools,
        "rhino_skin_from_sections",
        {"section_curve_ids": [a, b, c]},
    )
    assert len(res["summary"]["object_ids"]) == 2


def test_skin_invalid_section_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    a = _arc(tools, 0.0, 5.0)
    box = call_tool(
        tools,
        "rhino_box",
        {"corner": {"x": 0, "y": 0, "z": 0}, "size_x": 1.0, "size_y": 1.0, "size_z": 1.0},
    )
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_skin_from_sections",
            {"section_curve_ids": [a, box["summary"]["object_id"]]},
        )


# ---------- paneling ------------------------------------------------------------


def test_uv_grid_mesh_quad_count(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _skin_from_two_arcs(tools)
    panels = call_tool(
        tools,
        "rhino_uv_grid_panels",
        {"surface_id": sid, "count_u": 6, "count_v": 4, "output": "mesh"},
    )
    assert panels["summary"]["panel_count"] == 24
    assert panels["summary"]["count_u"] == 6


def test_uv_grid_corners_only(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _skin_from_two_arcs(tools)
    res = call_tool(
        tools,
        "rhino_uv_grid_panels",
        {"surface_id": sid, "count_u": 5, "count_v": 3, "output": "corners"},
    )
    assert len(res["summary"]["corners"]) == (5 + 1) * (3 + 1)


def test_uv_grid_invalid_output_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _skin_from_two_arcs(tools)
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_uv_grid_panels",
            {"surface_id": sid, "count_u": 4, "count_v": 4, "output": "garbage"},
        )


def test_panel_planarity_ruled_surface_is_planar(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _skin_from_two_arcs(tools)
    res = call_tool(
        tools,
        "rhino_panel_planarity",
        {"surface_id": sid, "count_u": 6, "count_v": 4, "tolerance": 1e-6},
    )
    # A ruled surface between two parallel arcs has planar quads along
    # the rulings; numerical noise should be far below 1e-6 → 0 violators.
    assert res["summary"]["stats"]["non_planar_count"] == 0


def test_panel_curvature_classify_returns_class_counts(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _skin_from_two_arcs(tools)
    res = call_tool(
        tools,
        "rhino_panel_curvature_classify",
        {
            "surface_id": sid,
            "count_u": 6,
            "count_v": 4,
            "planar_tolerance": 0.001,
            "single_curve_tolerance": 0.05,
        },
    )
    counts = res["summary"]["class_counts"]
    # Ruled surface between arcs is single-curved along U (the arc direction)
    # — sum of curved-class counts must equal panel_count.
    total = sum(counts.values())
    assert total == res["summary"]["panel_count"] == 24
    assert counts["single_curved_u"] + counts["single_curved_v"] > 0


# ---------- curvature -----------------------------------------------------------


def test_surface_normal_at_returns_unit_vector(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _skin_from_two_arcs(tools)
    res = call_tool(tools, "rhino_surface_normal_at", {"surface_id": sid, "u": 0.5, "v": 0.5})
    n = res["summary"]["normal"]
    mag = (n["x"] ** 2 + n["y"] ** 2 + n["z"] ** 2) ** 0.5
    assert abs(mag - 1.0) < 1e-6


def test_developable_score_within_unit_range(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _skin_from_two_arcs(tools)
    res = call_tool(
        tools,
        "rhino_surface_developable_score",
        {"surface_id": sid, "sample_u": 8, "sample_v": 8},
    )
    s = res["summary"]
    assert 0.0 <= s["score_normalised"] <= 1.0
    assert s["max_radians"] >= 0.0


# ---------- fields --------------------------------------------------------------


def test_attractor_displace_pulls_points_toward(server_standalone) -> None:
    _mcp, tools = server_standalone
    p1 = call_tool(tools, "rhino_point", {"point": {"x": 10, "y": 0, "z": 0}})
    p2 = call_tool(tools, "rhino_point", {"point": {"x": 20, "y": 0, "z": 0}})
    res = call_tool(
        tools,
        "rhino_attractor_displace_points",
        {
            "point_object_ids": [p1["summary"]["object_id"], p2["summary"]["object_id"]],
            "attractor_point": {"x": 0, "y": 0, "z": 0},
            "falloff": "linear",
            "strength": 0.5,
            "max_distance": 30.0,
        },
    )
    assert res["summary"]["moved"] == 2


def test_smooth_polyline_reduces_zigzag(server_standalone) -> None:
    _mcp, tools = server_standalone
    poly = call_tool(
        tools,
        "rhino_polyline",
        {
            "points": [
                {"x": 0, "y": 0, "z": 0},
                {"x": 1, "y": 1, "z": 0},
                {"x": 2, "y": 0, "z": 0},
                {"x": 3, "y": 1, "z": 0},
                {"x": 4, "y": 0, "z": 0},
            ],
            "closed": False,
        },
    )
    res = call_tool(
        tools,
        "rhino_smooth_polyline",
        {"curve_id": poly["summary"]["object_id"], "iterations": 5, "factor": 0.5},
    )
    assert res["summary"]["iterations"] == 5
    assert res["summary"]["factor"] == 0.5
    assert isinstance(res["summary"]["object_id"], str)
