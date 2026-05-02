"""Curve-tool tests."""

from __future__ import annotations

import math

import pytest

from tests.conftest import call_tool


def test_curve_length_circle(server_standalone) -> None:
    _mcp, tools = server_standalone
    circle = call_tool(tools, "rhino_circle", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 5.0})
    res = call_tool(tools, "rhino_curve_length", {"object_id": circle["summary"]["object_id"]})
    # Approximate: circumference 2πr ≈ 31.4159
    assert math.isclose(res["summary"]["length"], 2 * math.pi * 5.0, rel_tol=0.05)


def test_curve_point_at_validates_domain(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(
        tools, "rhino_line", {"start": {"x": 0, "y": 0, "z": 0}, "end": {"x": 10, "y": 0, "z": 0}}
    )
    # Convert line to curve via NURBS conversion: build a NURBS curve directly to test.
    nc = call_tool(
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
    nc_id = nc["summary"]["object_id"]
    # Mid-domain point eval should succeed.
    res = call_tool(tools, "rhino_curve_point_at", {"object_id": nc_id, "t": 0.5})
    assert "point" in res["summary"] and "tangent" in res["summary"]
    # Out-of-domain → parameter_error.
    with pytest.raises(Exception):  # noqa: B017
        call_tool(tools, "rhino_curve_point_at", {"object_id": nc_id, "t": 99.0})


def test_curve_split(server_standalone) -> None:
    _mcp, tools = server_standalone
    nc = call_tool(
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
    res = call_tool(
        tools,
        "rhino_curve_split",
        {"object_id": nc["summary"]["object_id"], "parameters": [0.5]},
    )
    assert len(res["summary"]["pieces"]) >= 1
