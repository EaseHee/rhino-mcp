"""Environment tool tests (sun_position, sun_path, shadow_project)."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_sun_position_seoul_solstice(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_sun_position",
        {
            "latitude": 37.5663,
            "longitude": 126.9779,
            "datetime_iso": "2026-06-21T12:00:00",
            "timezone_offset_h": 9.0,
        },
    )
    s = res["summary"]
    assert s["altitude_deg"] > 60
    assert s["is_above_horizon"] is True


def test_sun_position_arctic_winter_below_horizon(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_sun_position",
        {
            "latitude": 80.0,
            "longitude": 0.0,
            "datetime_iso": "2026-12-21T12:00:00",
            "timezone_offset_h": 0.0,
        },
    )
    assert res["summary"]["altitude_deg"] < 0
    assert res["summary"]["is_above_horizon"] is False


def test_sun_position_equator_noon_high(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_sun_position",
        {
            "latitude": 0.0,
            "longitude": 0.0,
            "datetime_iso": "2026-03-21T12:00:00",
            "timezone_offset_h": 0.0,
        },
    )
    assert res["summary"]["altitude_deg"] > 70


def test_sun_path_emits_polylines(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_sun_path",
        {
            "latitude": 37.5663,
            "longitude": 126.9779,
            "year": 2026,
            "months": [3, 6, 9, 12],
            "hours": [8, 12, 16],
            "radius": 50.0,
            "timezone_offset_h": 9.0,
        },
    )
    assert res["summary"]["month_count"] >= 1
    assert res["summary"]["sample_count"] >= 3


def test_shadow_project_with_zero_vector_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere = call_tool(
        tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 5}, "radius": 1.0}
    )
    sid = sphere["summary"]["object_id"]
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_shadow_project",
            {
                "object_ids": [sid],
                "sun_vector": {"x": 0, "y": 0, "z": 0},
                "ground_z": 0.0,
            },
        )


def test_shadow_project_emits_polygon(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere = call_tool(
        tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 5}, "radius": 1.0}
    )
    sid = sphere["summary"]["object_id"]
    res = call_tool(
        tools,
        "rhino_shadow_project",
        {
            "object_ids": [sid],
            "sun_vector": {"x": -0.3, "y": -0.3, "z": -1.0},
            "ground_z": 0.0,
        },
    )
    assert res["summary"]["shadow_count"] == 1
