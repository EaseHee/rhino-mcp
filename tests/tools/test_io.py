"""File I/O tool tests with temp paths."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import call_tool


def test_save_and_open_round_trip(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    # Create a sphere then save.
    call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 5.0})
    target = tmp_path / "round-trip.3dm"
    call_tool(tools, "rhino_save", {"path": str(target), "version": 8})
    assert target.exists() and target.stat().st_size > 0
    # Reopen.
    opened = call_tool(tools, "rhino_open", {"path": str(target)})
    assert opened["summary"]["object_count"] == 1


def test_export_obj_writes_file(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    # Mesh box has triangles → should export.
    call_tool(
        tools,
        "rhino_mesh_box",
        {
            "corner": {"x": 0, "y": 0, "z": 0},
            "size_x": 1,
            "size_y": 1,
            "size_z": 1,
        },
    )
    obj_path = tmp_path / "out.obj"
    result = call_tool(tools, "rhino_export_obj", {"path": str(obj_path)})
    assert obj_path.exists()
    text = obj_path.read_text()
    assert text.startswith("# rhino-mcp export")
    assert "v " in text
    assert "f " in text
    assert result["summary"]["path"] == str(obj_path)


def test_export_stl_writes_file(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    call_tool(
        tools,
        "rhino_mesh_box",
        {
            "corner": {"x": 0, "y": 0, "z": 0},
            "size_x": 1,
            "size_y": 1,
            "size_z": 1,
        },
    )
    stl_path = tmp_path / "out.stl"
    call_tool(tools, "rhino_export_stl", {"path": str(stl_path)})
    text = stl_path.read_text()
    assert text.startswith("solid rhino_mcp")
    assert text.rstrip().endswith("endsolid rhino_mcp")
