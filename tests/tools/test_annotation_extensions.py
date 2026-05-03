"""Tests for v0.3 annotation extensions (north_arrow, scale_bar, revision_cloud, callout)."""

from __future__ import annotations

from tests.conftest import call_tool


def test_north_arrow_simple(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_annotation_north_arrow",
        {"location": {"x": 0, "y": 0, "z": 0}, "size": 10.0, "angle_deg": 0.0, "style": "simple"},
    )
    assert res["summary"]["style"] == "simple"
    assert len(res["summary"]["object_ids"]) >= 2


def test_north_arrow_compass(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_annotation_north_arrow",
        {"location": {"x": 0, "y": 0, "z": 0}, "size": 10.0, "style": "compass"},
    )
    # 4 cardinal lines + label.
    assert len(res["summary"]["object_ids"]) >= 5


def test_scale_bar_emits_divisions(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_annotation_scale_bar",
        {"location": {"x": 0, "y": 0, "z": 0}, "total_length": 100.0, "divisions": 4, "scale_denominator": 100},
    )
    assert res["summary"]["divisions"] == 4
    # 4 rect polylines + 1 label.
    assert len(res["summary"]["object_ids"]) == 5


def test_revision_cloud_with_label(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_annotation_revision_cloud",
        {
            "boundary_points": [
                {"x": 0, "y": 0, "z": 0},
                {"x": 10, "y": 0, "z": 0},
                {"x": 10, "y": 10, "z": 0},
                {"x": 0, "y": 10, "z": 0},
            ],
            "revision_no": "R3",
            "date_iso": "2026-05-03",
        },
    )
    assert res["summary"]["revision_no"] == "R3"
    assert len(res["summary"]["object_ids"]) == 2  # cloud polyline + label


def test_callout_balloon(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_annotation_callout",
        {
            "target_point": {"x": 0, "y": 0, "z": 0},
            "leader_origin": {"x": 5, "y": 5, "z": 0},
            "text": "C-01",
            "style": "balloon",
        },
    )
    assert res["summary"]["style"] == "balloon"
    # leader + balloon circle + text.
    assert len(res["summary"]["object_ids"]) == 3
