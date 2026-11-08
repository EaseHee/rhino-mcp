"""File I/O tool tests with temp paths."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import rhino3dm as r3
from mcp.types import ImageContent, TextContent

from rhino_mcp.document import registry
from rhino_mcp.tools import context as tool_context
from rhino_mcp.utils.registry import Mode
from tests.conftest import call_tool
from tests.tools.test_display_capture import FakeCaptureBridge


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


# --- Viewport capture (bridge, fake transport) ---


def _bridge_mcp() -> tuple[Any, FakeCaptureBridge]:
    from rhino_mcp.server import build_server

    client = FakeCaptureBridge()
    tool_context.set_runtime(Mode.BRIDGE, client)  # type: ignore[arg-type]
    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=client)  # type: ignore[arg-type]
    return mcp, client


def _content(mcp: Any, name: str, payload: dict[str, Any]) -> tuple[list[ImageContent], dict[str, Any]]:
    result = asyncio.run(mcp.call_tool(name, {"args": payload}))
    blocks = list(result[0] if isinstance(result, tuple) else result)
    images = [b for b in blocks if isinstance(b, ImageContent)]
    texts = [b for b in blocks if isinstance(b, TextContent)]
    assert len(texts) == 1
    assert "image_base64" not in texts[0].text
    return images, json.loads(texts[0].text)


def test_screenshot_returns_image_content(tmp_path: Path) -> None:
    mcp, client = _bridge_mcp()
    out = str(tmp_path / "shot.png")
    images, payload = _content(mcp, "rhino_screenshot", {"path": out, "max_width": 512})
    assert len(images) == 1
    assert images[0].mimeType == "image/jpeg"
    method, params = client.calls[-1]
    assert method == "rhino.io.screenshot"
    assert params["max_width"] == 512
    assert params["format"] == "jpeg"
    assert params["as_base64"] is True
    assert payload["summary"]["path"] == out
    assert payload["summary"]["mime"] == "image/jpeg"
    assert "image_base64" not in payload["summary"]


def test_screenshot_legacy_as_base64_false_returns_summary_only(tmp_path: Path) -> None:
    mcp, client = _bridge_mcp()
    out = str(tmp_path / "shot.png")
    images, payload = _content(mcp, "rhino_screenshot", {"path": out, "as_base64": False})
    assert images == []
    assert client.calls[-1][1]["as_base64"] is False
    assert payload["summary"]["path"] == out


def test_screenshot_without_path_always_returns_image() -> None:
    mcp, client = _bridge_mcp()
    images, _ = _content(mcp, "rhino_screenshot", {"as_base64": False})
    assert len(images) == 1
    assert client.calls[-1][1]["path"] is None


def test_screenshot_legacy_mime_selects_png(tmp_path: Path) -> None:
    mcp, client = _bridge_mcp()
    images, _ = _content(
        mcp, "rhino_screenshot", {"path": str(tmp_path / "s.png"), "mime": "image/png"}
    )
    assert images[0].mimeType == "image/png"
    assert client.calls[-1][1]["format"] == "png"
    assert "mime" not in client.calls[-1][1]


def test_viewport_preview_returns_image_content() -> None:
    mcp, client = _bridge_mcp()
    images, payload = _content(
        mcp, "rhino_viewport_preview", {"selection_ids": ["a"], "jpeg_quality": 60}
    )
    assert len(images) == 1
    method, params = client.calls[-1]
    assert method == "rhino.io.viewport_preview"
    assert params["jpeg_quality"] == 60
    assert params["selection_ids"] == ["a"]
    assert payload["summary"]["bytes"] > 0


# --- Draco export (standalone) ---


def _mesh_box(tools: dict[str, Any], x: float = 0.0) -> None:
    call_tool(
        tools,
        "rhino_mesh_box",
        {"corner": {"x": x, "y": 0, "z": 0}, "size_x": 1, "size_y": 1, "size_z": 1},
    )


def test_export_draco_round_trip(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    _mesh_box(tools)
    source = registry().get("active").file3dm.Objects[0].Geometry
    drc = tmp_path / "box.drc"
    result = call_tool(tools, "rhino_export_draco", {"path": str(drc)})
    assert drc.exists() and drc.stat().st_size == result["summary"]["bytes"]
    back = r3.DracoCompression.DecompressByteArray(drc.read_bytes())
    assert isinstance(back, r3.Mesh)
    assert len(back.Vertices) == len(source.Vertices)
    # Draco stores triangles only, so each quad of the box comes back as two.
    assert back.Faces.Count == 2 * source.Faces.Count
    assert result["summary"]["vertex_count"] == len(source.Vertices)
    assert result["summary"]["mesh_count"] == 1


def test_export_draco_merges_all_meshes(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    _mesh_box(tools, 0.0)
    _mesh_box(tools, 5.0)
    single = len(registry().get("active").file3dm.Objects[0].Geometry.Vertices)
    drc = tmp_path / "two.drc"
    result = call_tool(tools, "rhino_export_draco", {"path": str(drc)})
    back = r3.DracoCompression.DecompressByteArray(drc.read_bytes())
    assert result["summary"]["mesh_count"] == 2
    assert len(back.Vertices) == result["summary"]["vertex_count"] == 2 * single


def test_export_draco_rejects_documents_without_meshes(server_standalone, tmp_path: Path) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_sphere", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0})
    with pytest.raises(Exception, match="object_ids"):
        call_tool(tools, "rhino_export_draco", {"path": str(tmp_path / "none.drc")})
    assert not (tmp_path / "none.drc").exists()


def test_export_draco_is_standalone_only(tmp_path: Path) -> None:
    mcp, _client = _bridge_mcp()
    with pytest.raises(Exception, match="standalone"):
        asyncio.run(mcp.call_tool("rhino_export_draco", {"args": {"path": str(tmp_path / "x.drc")}}))
