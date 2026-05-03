"""Daylight precision tests (DNI clear-sky model + BRE daylight factor)."""

from __future__ import annotations

from tests.conftest import call_tool


def test_dni_summer_noon_high_value(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_direct_irradiance",
        {
            "latitude": 37.5663,
            "longitude": 126.9779,
            "datetime_iso": "2026-06-21T12:00:00",
            "timezone_offset_h": 9.0,
            "altitude_m": 38.0,
            "turbidity": 2.5,
        },
    )
    s = res["summary"]
    assert s["altitude_deg"] > 70
    assert s["dni_w_per_m2"] > 800
    assert s["air_mass"] is not None and s["air_mass"] < 1.1


def test_dni_below_horizon_zero(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_direct_irradiance",
        {
            "latitude": 80.0,
            "longitude": 0.0,
            "datetime_iso": "2026-12-21T12:00:00",
            "timezone_offset_h": 0.0,
        },
    )
    assert res["summary"]["dni_w_per_m2"] == 0.0
    assert res["summary"]["is_above_horizon"] is False


def test_dni_high_turbidity_lower_than_clear(server_standalone) -> None:
    _mcp, tools = server_standalone
    base = {
        "latitude": 37.5663,
        "longitude": 126.9779,
        "datetime_iso": "2026-06-21T12:00:00",
        "timezone_offset_h": 9.0,
    }
    clear = call_tool(tools, "rhino_direct_irradiance", {**base, "turbidity": 1.5})
    hazy = call_tool(tools, "rhino_direct_irradiance", {**base, "turbidity": 6.0})
    assert hazy["summary"]["dni_w_per_m2"] < clear["summary"]["dni_w_per_m2"]


def test_daylight_factor_acceptable_range(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_daylight_factor",
        {
            "window_area_m2": 4.5,
            "visible_sky_angle_deg": 60.0,
            "glass_transmittance": 0.7,
            "maintenance_factor": 0.9,
            "total_surface_area_m2": 90.0,
            "average_reflectance": 0.5,
        },
    )
    df = res["summary"]["daylight_factor_pct"]
    assert 1.5 < df < 4.0
    assert "rating" in res["summary"]


def test_daylight_factor_deficient_label(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_daylight_factor",
        {
            "window_area_m2": 0.5,
            "visible_sky_angle_deg": 30.0,
            "glass_transmittance": 0.5,
            "maintenance_factor": 0.7,
            "total_surface_area_m2": 200.0,
            "average_reflectance": 0.3,
        },
    )
    assert res["summary"]["daylight_factor_pct"] < 2.0
    assert "deficient" in res["summary"]["rating"]
