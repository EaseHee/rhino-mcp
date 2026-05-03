"""Drawing tool tests (sheet_create, title_block_add, bridge gating)."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_sheet_create_writes_metadata(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_drawing_sheet_create",
        {
            "name": "A-001",
            "width_mm": 297.0,
            "height_mm": 210.0,
            "scale_denominator": 50,
            "origin": {"x": 0, "y": 0, "z": 0},
        },
    )
    summary = res["summary"]
    assert summary["name"] == "A-001"
    assert summary["width_mm"] == 297.0
    assert summary["scale_denominator"] == 50
    assert summary["layer"] == "Sheets::A-001"


def test_sheet_create_persists_metadata(server_standalone) -> None:
    """Sheet metadata is stored on the rectangle's user_text and accessible via rhino3dm."""
    from rhino_mcp.document import registry

    _mcp, tools = server_standalone
    sheet = call_tool(
        tools,
        "rhino_drawing_sheet_create",
        {"name": "A-101", "width_mm": 420.0, "height_mm": 297.0},
    )
    sid = sheet["summary"]["sheet_id"]
    handle = registry().get_or_create("active")
    obj = handle.file3dm.Objects.FindId(sid)
    assert obj is not None
    assert obj.Attributes.GetUserString("sheet_name") == "A-101"
    assert obj.Attributes.GetUserString("sheet_width_mm") == "420.0"


def test_title_block_emits_objects(server_standalone) -> None:
    _mcp, tools = server_standalone
    sheet = call_tool(
        tools,
        "rhino_drawing_sheet_create",
        {"name": "A-002", "width_mm": 420.0, "height_mm": 297.0, "scale_denominator": 100},
    )
    sid = sheet["summary"]["sheet_id"]
    res = call_tool(
        tools,
        "rhino_drawing_title_block_add",
        {
            "sheet_id": sid,
            "project": "Test",
            "title": "Plan",
            "scale_text": "1:100",
            "date_iso": "2026-05-03",
            "drawn_by": "qa",
            "sheet_no": "A-002",
            "north_arrow_angle_deg": 0.0,
        },
    )
    assert len(res["summary"]["object_ids"]) > 5  # rect + labels + arrow + scale bar


def test_view_place_unsupported_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    sheet = call_tool(
        tools,
        "rhino_drawing_sheet_create",
        {"name": "A-003", "width_mm": 420.0, "height_mm": 297.0},
    )
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_drawing_view_place",
            {
                "sheet_id": sheet["summary"]["sheet_id"],
                "object_ids": ["00000000-0000-0000-0000-000000000000"],
                "view_plane": "Top",
                "target_origin": {"x": 100, "y": 100, "z": 0},
            },
        )
