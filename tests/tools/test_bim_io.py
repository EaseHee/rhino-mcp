"""BIM I/O tool tests (metadata + bridge gating)."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def _make_sphere(tools) -> str:
    res = call_tool(
        tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0}
    )
    return res["summary"]["object_id"]


def test_bim_metadata_writes_user_text(server_standalone) -> None:
    from rhino_mcp.document import registry

    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    res = call_tool(
        tools,
        "rhino_bim_metadata_set",
        {
            "object_ids": [sid],
            "entity_type": "IfcWallStandardCase",
            "pset_name": "Pset_WallCommon",
            "properties": {"FireRating": "2h", "LoadBearing": "true"},
        },
    )
    assert res["summary"]["entity_type"] == "IfcWallStandardCase"
    assert res["summary"]["property_count"] == 2
    obj = registry().get_or_create("active").file3dm.Objects.FindId(sid)
    assert obj.Attributes.GetUserString("ifc_entity") == "IfcWallStandardCase"
    assert obj.Attributes.GetUserString("Pset_WallCommon::FireRating") == "2h"


def test_export_ifc_unsupported_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_export_ifc",
            {"path": "/tmp/test.ifc", "schema_version": "IFC4"},
        )


def test_export_ifc_rejects_unknown_schema(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_export_ifc",
            {"path": "/tmp/x.ifc", "schema_version": "IFC9"},
        )


def test_import_ifc_unsupported_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(tools, "rhino_import_ifc", {"path": "/tmp/test.ifc"})
