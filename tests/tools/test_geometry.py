"""Geometry-tool integration tests against an in-memory rhino3dm document."""

from __future__ import annotations

from tests.conftest import call_tool


def test_add_point(server_standalone) -> None:
    _mcp, tools = server_standalone
    result = call_tool(
        tools, "rhino_point", {"point": {"x": 1.0, "y": 2.0, "z": 3.0}, "doc_id": "p"}
    )
    assert result["summary"]["kind"] == "Point"
    assert result["summary"]["object_id"]


def test_add_line_rejects_zero_length(server_standalone) -> None:
    import pytest

    _mcp, tools = server_standalone
    with pytest.raises(Exception):  # noqa: B017  # ToolError / ValueError
        call_tool(
            tools,
            "rhino_line",
            {"start": {"x": 0, "y": 0, "z": 0}, "end": {"x": 0, "y": 0, "z": 0}},
        )


def test_add_circle_rectangle_polygon(server_standalone) -> None:
    _mcp, tools = server_standalone
    circle = call_tool(
        tools, "rhino_circle", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 5.0}
    )
    rect = call_tool(
        tools,
        "rhino_rectangle",
        {"corner": {"x": 0, "y": 0, "z": 0}, "width": 4.0, "height": 2.0},
    )
    poly = call_tool(
        tools,
        "rhino_polygon",
        {"center": {"x": 0, "y": 0, "z": 0}, "radius": 5.0, "sides": 6},
    )
    for r in (circle, rect, poly):
        assert r["summary"]["object_id"]
        assert r["summary"]["bounding_box"]["max"]["x"] >= r["summary"]["bounding_box"]["min"]["x"]


def test_add_polyline_closed(server_standalone) -> None:
    _mcp, tools = server_standalone
    pts = [
        {"x": 0, "y": 0, "z": 0},
        {"x": 1, "y": 0, "z": 0},
        {"x": 1, "y": 1, "z": 0},
        {"x": 0, "y": 1, "z": 0},
    ]
    r = call_tool(tools, "rhino_polyline", {"points": pts, "closed": True})
    assert r["summary"]["kind"] == "Polyline"


def test_add_arc_helix_spiral(server_standalone) -> None:
    _mcp, tools = server_standalone
    arc = call_tool(
        tools,
        "rhino_arc",
        {"center": {"x": 0, "y": 0, "z": 0}, "radius": 5.0, "angle_degrees": 90},
    )
    helix = call_tool(
        tools,
        "rhino_helix",
        {
            "center": {"x": 0, "y": 0, "z": 0},
            "radius": 2.0,
            "pitch": 1.0,
            "turns": 3,
        },
    )
    spiral = call_tool(
        tools,
        "rhino_spiral",
        {
            "center": {"x": 0, "y": 0, "z": 0},
            "start_radius": 1.0,
            "end_radius": 5.0,
            "pitch": 0.5,
            "turns": 4,
        },
    )
    for r in (arc, helix, spiral):
        assert r["summary"]["object_id"]


def test_nurbs_curve_validation(server_standalone) -> None:
    import pytest

    _mcp, tools = server_standalone
    # Two control points + degree 3 should fail with parameter_error.
    with pytest.raises(Exception):  # noqa: B017
        call_tool(
            tools,
            "rhino_nurbs_curve",
            {
                "control_points": [{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 0, "z": 0}],
                "degree": 3,
            },
        )

    ok = call_tool(
        tools,
        "rhino_nurbs_curve",
        {
            "control_points": [
                {"x": 0, "y": 0, "z": 0},
                {"x": 1, "y": 1, "z": 0},
                {"x": 2, "y": 0, "z": 0},
                {"x": 3, "y": 1, "z": 0},
            ],
            "degree": 3,
        },
    )
    assert ok["summary"]["object_id"]
