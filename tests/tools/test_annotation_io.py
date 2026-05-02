"""Annotation + IO edge-case tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import call_tool


def test_text_dot(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_text_dot",
        {"text": "Origin", "location": {"x": 0, "y": 0, "z": 0}},
    )
    assert res["summary"]["kind"] == "TextDot"


def test_text_falls_back_to_dot(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_text",
        {"text": "Hello", "location": {"x": 1, "y": 2, "z": 0}, "height": 1.0},
    )
    assert res["summary"]["kind"] == "Text"


def test_import_3dm_round_trip(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 2.0})
    target = tmp_path / "imp.3dm"
    call_tool(tools, "rhino_save", {"path": str(target)})
    imported = call_tool(tools, "rhino_import", {"path": str(target)})
    assert "imported_doc_id" in imported["summary"]


def test_import_unknown_extension_in_standalone_raises(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    fake = tmp_path / "broken.step"
    fake.write_text("dummy")
    with pytest.raises(Exception):  # noqa: B017
        call_tool(tools, "rhino_import", {"path": str(fake)})
