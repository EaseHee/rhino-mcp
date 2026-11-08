"""MCP resources exposing read-only scene context.

Resources let a client pull document context (scene summary, layer tree,
selection, RhinoScript reference pages) without spending a tool call.

* ``rhino://scene/summary`` — object counts by type and layer, units, bbox.
* ``rhino://layers`` — nested layer tree.
* ``rhino://selection`` — current selection (bridge only).
* ``rhinoscript://{function}`` — Markdown reference page for one
  ``rhinoscriptsyntax`` function.

Standalone reads the active ``rhino3dm`` document; bridge mode forwards to
the existing ``rhino.query.*`` handlers. Bridge round-trips run on a worker
thread so the MCP event loop is never blocked by Rhino.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import anyio

from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

log = get_logger("resources")

_JSON = "application/json"
_MARKDOWN = "text/markdown"
_NIL_UUID = "00000000-0000-0000-0000-000000000000"

SCENE_SUMMARY_URI = "rhino://scene/summary"
LAYERS_URI = "rhino://layers"
SELECTION_URI = "rhino://selection"
RHINOSCRIPT_TEMPLATE = "rhinoscript://{function}"


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)


def _probe_bridge() -> bool:
    """Return True when a bridge is usable, trying lazy promotion like tools do.

    ``Runtime.require_bridge`` re-detects at most once per
    ``RHINO_MCP_REDETECT_COOLDOWN`` window, so a server that started
    standalone picks up a Rhino launched later without hammering transports.
    """
    from rhino_mcp.tools.context import runtime
    from rhino_mcp.utils.error_handling import ToolError

    rt = runtime()
    if rt.mode is Mode.BRIDGE:
        return True
    # An explicit standalone override must not be undone by a resource read.
    if os.environ.get("RHINO_MCP_FORCE_MODE", "").lower() == "standalone":
        return False
    try:
        rt.require_bridge()
    except ToolError:
        return False
    return rt.bridge is not None


async def _bridge_active() -> bool:
    # Detection may block on transport connects; keep it off the event loop.
    return await anyio.to_thread.run_sync(_probe_bridge)


async def _bridge(method: str, params: dict[str, Any]) -> dict[str, Any]:
    from rhino_mcp.tools._helpers import bridge_call

    return await anyio.to_thread.run_sync(bridge_call, method, params)


def _rgb(color: Any) -> dict[str, int]:
    if isinstance(color, tuple):
        return {"r": int(color[0]), "g": int(color[1]), "b": int(color[2])}
    return {"r": int(color.R), "g": int(color.G), "b": int(color.B)}


def _layer_path(layer: Any) -> str:
    full = getattr(layer, "FullPath", "") or ""
    return str(full or layer.Name)


def standalone_scene_summary(doc_id: str = "active") -> dict[str, Any]:
    """Summarise a standalone document: counts by type and layer, units, bbox."""
    from rhino_mcp.tools._helpers import doc
    from rhino_mcp.tools.document_config import _UNITS_ENUM_TO_NAME

    handle = doc(doc_id)
    # rhino3dm stubs miss table indexing / len; treat the file as dynamic.
    f: Any = handle.file3dm
    layer_names = [_layer_path(f.Layers[i]) for i in range(len(f.Layers))]
    by_type: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for i in range(len(f.Objects)):
        obj = f.Objects[i]
        kind = type(obj.Geometry).__name__
        by_type[kind] = by_type.get(kind, 0) + 1
        idx = obj.Attributes.LayerIndex
        layer = layer_names[idx] if 0 <= idx < len(layer_names) else f"<index {idx}>"
        by_layer[layer] = by_layer.get(layer, 0) + 1
        bb = obj.Geometry.GetBoundingBox()
        if bb is None or not bb.IsValid:
            continue
        for axis, attr in enumerate(("X", "Y", "Z")):
            lo[axis] = min(lo[axis], getattr(bb.Min, attr))
            hi[axis] = max(hi[axis], getattr(bb.Max, attr))
    bbox: dict[str, dict[str, float]] | None = None
    if lo[0] != float("inf"):
        bbox = {
            "min": {"x": lo[0], "y": lo[1], "z": lo[2]},
            "max": {"x": hi[0], "y": hi[1], "z": hi[2]},
        }
    settings = f.Settings
    unit_int = int(settings.ModelUnitSystem)
    return {
        "mode": Mode.STANDALONE.value,
        "doc_id": handle.doc_id,
        "total_objects": len(f.Objects),
        "counts_by_type": by_type,
        "counts_by_layer": by_layer,
        "layer_count": len(f.Layers),
        "units": _UNITS_ENUM_TO_NAME.get(unit_int, str(settings.ModelUnitSystem)),
        "bounding_box": bbox,
    }


def standalone_layer_tree(doc_id: str = "active") -> dict[str, Any]:
    """Build a nested layer tree from a standalone document's parent links."""
    from rhino_mcp.tools._helpers import doc

    handle = doc(doc_id)
    f: Any = handle.file3dm
    counts: dict[int, int] = {}
    for i in range(len(f.Objects)):
        idx = f.Objects[i].Attributes.LayerIndex
        counts[idx] = counts.get(idx, 0) + 1
    nodes: dict[str, dict[str, Any]] = {}
    parents: dict[str, str] = {}
    order: list[str] = []
    for i in range(len(f.Layers)):
        lay: Any = f.Layers[i]
        lid = str(lay.Id)
        nodes[lid] = {
            "index": i,
            "name": lay.Name,
            "full_path": _layer_path(lay),
            "color": _rgb(lay.Color),
            "visible": bool(lay.Visible),
            "locked": bool(getattr(lay, "Locked", False)),
            "object_count": counts.get(i, 0),
            "children": [],
        }
        parents[lid] = str(getattr(lay, "ParentLayerId", _NIL_UUID))
        order.append(lid)
    roots: list[dict[str, Any]] = []
    for lid in order:
        parent = nodes.get(parents[lid])
        if parent is None:
            roots.append(nodes[lid])
        else:
            parent["children"].append(nodes[lid])
    return {
        "mode": Mode.STANDALONE.value,
        "doc_id": handle.doc_id,
        "layer_count": len(order),
        "layers": roots,
    }


def tree_from_paths(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nest a flat layer list by its ``full_path`` (``::`` separated) entries."""
    by_path: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in sorted(layers, key=lambda r: str(r.get("full_path") or r.get("name") or "")):
        node = dict(row)
        node["children"] = []
        path = str(row.get("full_path") or row.get("name") or "")
        by_path[path] = node
        parent_path, sep, _ = path.rpartition("::")
        parent = by_path.get(parent_path) if sep else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    return roots


def _short_units(raw: Any) -> Any:
    """Map RhinoCommon unit names (``Millimeters``) to the standalone short form (``mm``)."""
    from rhino_mcp.tools.document_config import _UNITS_ENUM_TO_NAME, _UNITS_NAME_TO_ENUM

    if not isinstance(raw, str):
        return raw
    enum: Any = _UNITS_NAME_TO_ENUM.get(raw.strip().lower())
    if enum is None:
        return raw
    return _UNITS_ENUM_TO_NAME.get(int(enum), raw)


def _layer_counts(layers: Any) -> dict[str, int] | None:
    """Per-layer object counts keyed by full path; ``None`` when rows carry no counts."""
    if not isinstance(layers, list) or not all(
        isinstance(row, dict) and "object_count" in row for row in layers
    ):
        return None
    counts: dict[str, int] = {}
    for row in layers:
        n = int(row.get("object_count") or 0)
        if n > 0:
            counts[str(row.get("full_path") or row.get("name") or "")] = n
    return counts


# Bridge summary keys renamed or dropped so the payload matches the standalone shape.
_BRIDGE_SUMMARY_CONSUMED = frozenset({"type_counts", "layers", "total_objects", "layer_count", "units"})


async def bridge_scene_summary() -> dict[str, Any]:
    """Normalise ``rhino.query.document_summary`` to the standalone summary shape.

    The C# handler returns ``total_objects / type_counts / layer_count /
    layers / file_path / units`` without per-layer counts or a bbox, so
    counts come from ``rhino.query.layer_list`` and ``bounding_box`` is null.
    Unrecognised extra keys (``file_path``) are kept.
    """
    result = await _bridge("rhino.query.document_summary", {"doc_id": "active"})
    raw = result.get("summary", result) if isinstance(result, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    layers = raw.get("layers")
    by_layer = _layer_counts(layers)
    if by_layer is None:
        try:
            listed = await _bridge("rhino.query.layer_list", {"doc_id": "active"})
            listed_summary = listed.get("summary", listed) if isinstance(listed, dict) else {}
            by_layer = _layer_counts(listed_summary.get("layers"))
        except Exception as exc:
            log.debug("layer_list for scene summary failed: %s", exc)
    layer_count = raw.get("layer_count")
    if layer_count is None and isinstance(layers, list):
        layer_count = len(layers)
    payload: dict[str, Any] = {
        "mode": Mode.BRIDGE.value,
        "doc_id": "active",
        "total_objects": raw.get("total_objects", 0),
        "counts_by_type": dict(raw.get("type_counts") or {}),
        "counts_by_layer": by_layer,
        "layer_count": layer_count,
        "units": _short_units(raw.get("units")),
        "bounding_box": raw.get("bounding_box"),
    }
    for key, value in raw.items():
        if key not in payload and key not in _BRIDGE_SUMMARY_CONSUMED:
            payload[key] = value
    return payload


async def scene_summary() -> str:
    """Object counts by type / layer, model units, and the scene bounding box."""
    if await _bridge_active():
        return _dumps(await bridge_scene_summary())
    return _dumps(standalone_scene_summary())


async def layer_tree() -> str:
    """Nested layer tree with colour, visibility, lock state and object counts."""
    if await _bridge_active():
        result = await _bridge("rhino.query.layer_list", {"doc_id": "active"})
        summary = result.get("summary", result) if isinstance(result, dict) else {}
        flat = summary.get("layers", []) if isinstance(summary, dict) else []
        return _dumps({
            "mode": Mode.BRIDGE.value,
            "layer_count": len(flat),
            "layers": tree_from_paths(flat),
        })
    return _dumps(standalone_layer_tree())


async def selection() -> str:
    """Objects currently selected in the live Rhino session (bridge only)."""
    if await _bridge_active():
        result = await _bridge(
            "rhino.query.selected_objects",
            {"doc_id": "active", "include_attributes": False},
        )
        return _dumps({"mode": Mode.BRIDGE.value, **result})
    return _dumps({
        "mode": Mode.STANDALONE.value,
        "available": False,
        "count": 0,
        "objects": [],
        "reason": (
            "Selection is a live-Rhino concept; standalone (rhino3dm) documents have "
            "no selection state. Start Rhino 8 or 9 with the rhino-mcp plugin to use this resource."
        ),
    })


def rhinoscript_function(function: str) -> str:
    """Markdown reference page for one ``rhinoscriptsyntax`` function."""
    from rhino_mcp.tools.rhinoscript_docs import (
        function_details,
        function_markdown,
        search_functions,
    )

    details = function_details(function)
    if details is None:
        hints = [r["name"] for r in search_functions(function, 5)]
        suggestion = f" Did you mean: {', '.join(hints)}?" if hints else ""
        raise ValueError(f"Unknown RhinoScript function {function!r}.{suggestion}")
    return function_markdown(details)


def register_resources(mcp: FastMCP) -> int:
    """Register every resource and template on ``mcp``. Returns the count."""
    mcp.resource(
        SCENE_SUMMARY_URI,
        name="scene_summary",
        description="Object counts by type and layer, model units and scene bounding box.",
        mime_type=_JSON,
    )(scene_summary)
    mcp.resource(
        LAYERS_URI,
        name="layers",
        description="Nested layer tree (colour, visibility, lock state, object counts).",
        mime_type=_JSON,
    )(layer_tree)
    mcp.resource(
        SELECTION_URI,
        name="selection",
        description="Objects selected in the live Rhino session (bridge only).",
        mime_type=_JSON,
    )(selection)
    mcp.resource(
        RHINOSCRIPT_TEMPLATE,
        name="rhinoscript_function",
        description="RhinoScript (rhinoscriptsyntax) reference page for one function, e.g. rhinoscript://AddPoint.",
        mime_type=_MARKDOWN,
    )(rhinoscript_function)
    return 4
