"""MCP resources: scene summary, layer tree, selection, RhinoScript docs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import rhino3dm as r3

from rhino_mcp.bridge.rhino_connection import BridgeClient
from tests.conftest import call_tool

_STANDALONE_SUMMARY_KEYS = {
    "mode", "doc_id", "total_objects", "counts_by_type", "counts_by_layer",
    "layer_count", "units", "bounding_box",
}


@pytest.fixture(autouse=True)
def detect_calls(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Stub bridge auto-detection so resource reads never dial real transports.

    Tests append a client to the returned list to make the next detection succeed.
    """
    queue: list[Any] = []
    calls: list[Any] = []

    def _auto(cls: Any, timeout: float = 5.0) -> Any:
        calls.append(timeout)
        return queue.pop(0) if queue else None

    monkeypatch.setattr(BridgeClient, "auto", classmethod(_auto))
    calls_and_queue: list[Any] = [calls, queue]
    return calls_and_queue


def _read(mcp: Any, uri: str) -> tuple[str, str | None]:
    contents = list(asyncio.run(mcp.read_resource(uri)))
    assert len(contents) == 1
    return contents[0].content, contents[0].mime_type


@pytest.fixture
def opened_scene(server_standalone, tmp_path: Path):
    """Write a small .3dm (two layers, nested child, three objects) and open it."""
    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Meters
    walls = r3.Layer()
    walls.Name = "Walls"
    walls_idx = model.Layers.Add(walls)
    inner = r3.Layer()
    inner.Name = "Inner"
    inner.ParentLayerId = model.Layers[walls_idx].Id
    inner_idx = model.Layers.Add(inner)

    attrs = r3.ObjectAttributes()
    attrs.LayerIndex = walls_idx
    model.Objects.AddPoint(r3.Point3d(-1, -2, -3), attrs)
    model.Objects.AddPoint(r3.Point3d(4, 5, 6), attrs)
    inner_attrs = r3.ObjectAttributes()
    inner_attrs.LayerIndex = inner_idx
    model.Objects.AddSphere(r3.Sphere(r3.Point3d(0, 0, 0), 1.0), inner_attrs)
    path = tmp_path / "scene.3dm"
    assert model.Write(str(path), 8)

    mcp, tools = server_standalone
    # Resources reflect the default "active" document, like doc_id-less tools.
    call_tool(tools, "rhino_open", {"path": str(path), "doc_id": "active"})
    return mcp


def test_resources_are_listed(server_standalone) -> None:
    mcp, _ = server_standalone
    uris = {str(r.uri): r for r in asyncio.run(mcp.list_resources())}
    assert {"rhino://scene/summary", "rhino://layers", "rhino://selection"} <= set(uris)
    assert all(uris[u].mimeType == "application/json" for u in uris)
    templates = {t.uriTemplate: t for t in asyncio.run(mcp.list_resource_templates())}
    assert "rhinoscript://{function}" in templates
    assert templates["rhinoscript://{function}"].mimeType == "text/markdown"


def test_scene_summary_standalone(opened_scene) -> None:
    text, mime = _read(opened_scene, "rhino://scene/summary")
    assert mime == "application/json"
    data = json.loads(text)
    assert data["mode"] == "standalone"
    assert set(data) == _STANDALONE_SUMMARY_KEYS
    assert data["total_objects"] == 3
    assert data["counts_by_type"]["Point"] == 2
    assert data["counts_by_layer"] == {"Walls": 2, "Walls::Inner": 1}
    assert data["units"] == "m"
    bbox = data["bounding_box"]
    assert bbox["min"] == {"x": -1.0, "y": -2.0, "z": -3.0}
    assert bbox["max"] == {"x": 4.0, "y": 5.0, "z": 6.0}


def test_scene_summary_empty_doc(server_standalone) -> None:
    mcp, _ = server_standalone
    data = json.loads(_read(mcp, "rhino://scene/summary")[0])
    assert data["total_objects"] == 0
    assert data["bounding_box"] is None


def test_layer_tree_nests_children(opened_scene) -> None:
    data = json.loads(_read(opened_scene, "rhino://layers")[0])
    assert data["layer_count"] == 2
    (walls,) = data["layers"]
    assert walls["name"] == "Walls" and walls["object_count"] == 2
    (inner,) = walls["children"]
    assert inner["full_path"] == "Walls::Inner" and inner["object_count"] == 1


def test_selection_standalone_explains(server_standalone) -> None:
    mcp, _ = server_standalone
    data = json.loads(_read(mcp, "rhino://selection")[0])
    assert data["available"] is False
    assert data["count"] == 0
    assert "standalone" in data["reason"]


def test_rhinoscript_template(server_standalone) -> None:
    mcp, _ = server_standalone
    text, mime = _read(mcp, "rhinoscript://AddPoint")
    assert mime == "text/markdown"
    assert text.startswith("# rs.AddPoint")
    assert "AddPoint(point" in text
    assert "## Example" in text


def test_rhinoscript_template_unknown(server_standalone) -> None:
    mcp, _ = server_standalone
    with pytest.raises(Exception, match="Unknown RhinoScript function"):
        _read(mcp, "rhinoscript://NoSuchFunctionXyz")


def _cs_layer(index: int, name: str, full_path: str, **extra: Any) -> dict[str, Any]:
    row = {
        "index": index,
        "name": name,
        "full_path": full_path,
        "color": {"r": 0, "g": 0, "b": 0},
        "visible": True,
        "locked": False,
    }
    row.update(extra)
    return row


class _FakeBridge:
    """Responses shaped exactly like QueryHandler.cs DocumentSummary / LayerList."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def is_alive(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(method)
        if method == "rhino.query.document_summary":
            layers = [_cs_layer(0, "Root", "Root"), _cs_layer(1, "Child", "Root::Child")]
            return {
                "summary": {
                    "total_objects": 7,
                    "type_counts": {"Brep": 4, "Curve": 3},
                    "layer_count": len(layers),
                    "layers": layers,
                    "file_path": "C:/models/site.3dm",
                    "units": "Millimeters",
                },
                "text": "Document: 7 objects, 2 layers",
            }
        if method == "rhino.query.layer_list":
            layers = [
                _cs_layer(1, "Child", "Root::Child", object_count=3),
                _cs_layer(0, "Root", "Root", object_count=4),
            ]
            return {"summary": {"count": len(layers), "layers": layers}, "text": "2 layers"}
        if method == "rhino.query.selected_objects":
            return {"count": 1, "objects": [{"id": "abc"}]}
        raise AssertionError(method)


def test_resources_forward_to_bridge() -> None:
    from rhino_mcp.server import build_server
    from rhino_mcp.utils.registry import Mode

    bridge = _FakeBridge()
    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=bridge)  # type: ignore[arg-type]
    layers = json.loads(_read(mcp, "rhino://layers")[0])
    assert layers["layer_count"] == 2
    assert layers["layers"][0]["children"][0]["name"] == "Child"
    selection = json.loads(_read(mcp, "rhino://selection")[0])
    assert selection["count"] == 1 and selection["mode"] == "bridge"


def test_bridge_scene_summary_matches_standalone_shape(server_standalone) -> None:
    from rhino_mcp.server import build_server
    from rhino_mcp.utils.registry import Mode

    standalone_mcp, _ = server_standalone
    standalone = json.loads(_read(standalone_mcp, "rhino://scene/summary")[0])

    bridge = _FakeBridge()
    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=bridge)  # type: ignore[arg-type]
    data = json.loads(_read(mcp, "rhino://scene/summary")[0])

    # Same key set as standalone; file_path is the only bridge-only extra.
    assert set(data) - {"file_path"} == set(standalone) == _STANDALONE_SUMMARY_KEYS
    assert data["mode"] == "bridge"
    assert data["total_objects"] == 7
    assert data["counts_by_type"] == {"Brep": 4, "Curve": 3}
    assert data["counts_by_layer"] == {"Root": 4, "Root::Child": 3}
    assert data["layer_count"] == 2
    assert data["units"] == "mm"
    assert data["bounding_box"] is None
    assert data["file_path"] == "C:/models/site.3dm"
    assert bridge.calls == ["rhino.query.document_summary", "rhino.query.layer_list"]


def test_resources_promote_lazily_to_bridge(server_standalone, detect_calls, monkeypatch) -> None:
    # conftest forces standalone for the suite; lazy promotion needs auto mode.
    monkeypatch.delenv("RHINO_MCP_FORCE_MODE", raising=False)
    calls, queue = detect_calls
    mcp, _ = server_standalone
    bridge = _FakeBridge()
    queue.append(bridge)
    data = json.loads(_read(mcp, "rhino://scene/summary")[0])
    assert data["mode"] == "bridge"
    assert len(calls) == 1
    assert "rhino.query.document_summary" in bridge.calls


def test_forced_standalone_blocks_resource_promotion(
    server_standalone, detect_calls, monkeypatch
) -> None:
    calls, queue = detect_calls
    mcp, _ = server_standalone
    queue.append(_FakeBridge())
    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")
    data = json.loads(_read(mcp, "rhino://scene/summary")[0])
    assert data["mode"] == "standalone"
    assert calls == []


def test_resource_promotion_respects_cooldown(server_standalone, detect_calls, monkeypatch) -> None:
    monkeypatch.delenv("RHINO_MCP_FORCE_MODE", raising=False)
    calls, _ = detect_calls
    mcp, _ = server_standalone
    for _ in range(3):
        data = json.loads(_read(mcp, "rhino://scene/summary")[0])
        assert data["mode"] == "standalone"
    # One detection attempt; the next two reads fall inside RHINO_MCP_REDETECT_COOLDOWN.
    assert len(calls) == 1


def test_tree_from_paths_bridge_shape() -> None:
    from rhino_mcp.resources import tree_from_paths

    roots = tree_from_paths([
        {"name": "B", "full_path": "A::B"},
        {"name": "A", "full_path": "A"},
        {"name": "C", "full_path": "A::B::C"},
        {"name": "D", "full_path": "D"},
    ])
    assert [r["name"] for r in roots] == ["A", "D"]
    assert roots[0]["children"][0]["children"][0]["name"] == "C"
