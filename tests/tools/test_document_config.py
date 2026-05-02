"""Document config tool tests (units, tolerance, origin) + summary extension."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_units_get_default_is_known(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "rhino_document_units_get", {})
    assert "units" in res["summary"]


def test_units_set_changes_summary(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_document_units_set", {"units": "mm", "scale_existing": False})
    g = call_tool(tools, "rhino_document_units_get", {})
    assert g["summary"]["units"] == "mm"

    call_tool(tools, "rhino_document_units_set", {"units": "m", "scale_existing": False})
    g2 = call_tool(tools, "rhino_document_units_get", {})
    assert g2["summary"]["units"] == "m"


def test_units_set_unknown_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(tools, "rhino_document_units_set", {"units": "fathoms"})


def test_tolerance_round_trip(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(
        tools,
        "rhino_tolerance_set",
        {"absolute": 0.0025, "angle_degrees": 0.5, "relative": 0.01},
    )
    g = call_tool(tools, "rhino_tolerance_get", {})
    assert abs(g["summary"]["absolute"] - 0.0025) < 1e-9
    # angle stored in radians on rhino3dm; reading degrees should be ~0.5.
    assert abs(g["summary"]["angle_degrees"] - 0.5) < 1e-3


def test_origin_set_reference_does_not_move_geometry(server_standalone) -> None:
    _mcp, tools = server_standalone
    sphere = call_tool(
        tools,
        "rhino_sphere",
        {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0},
    )
    sid = sphere["summary"]["object_id"]
    call_tool(
        tools,
        "rhino_origin_set",
        {"base_point": {"x": 100, "y": 200, "z": 0}, "mode": "reference"},
    )
    info = call_tool(tools, "rhino_object_info", {"object_id": sid})
    bbox = info["summary"]["bbox"]
    # Sphere bbox should still be near origin (reference mode does not translate).
    assert bbox["min"]["x"] < 0 and bbox["max"]["x"] > 0


def test_document_summary_includes_extended_fields(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "rhino_document_summary", {})
    s = res["summary"]
    assert "units" in s
    assert "tolerances" in s
    assert "base_point" in s
    assert "layer_tree_depth" in s
