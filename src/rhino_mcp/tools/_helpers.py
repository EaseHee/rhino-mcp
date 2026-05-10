"""Tool-implementation helpers used across modules."""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import rhino3dm as r3

from rhino_mcp.document import DocumentHandle, registry
from rhino_mcp.models.geometry_types import Point3dModel, Vector3dModel
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode
from rhino_mcp.utils.serialization import bbox_to_dict

_tool_log = get_logger("tool")


def _resolve_max_object_ids() -> int:
    """Per-tool ceiling on multi-id input arrays (override via env)."""
    raw = os.environ.get("RHINO_MCP_MAX_OBJECT_IDS")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return 500


MAX_OBJECT_IDS: int = _resolve_max_object_ids()
"""Default upper bound for any ``object_ids`` (or peer) input array.

Tools annotate their multi-id Pydantic fields with ``max_length=MAX_OBJECT_IDS``
so a Pydantic ``ValidationError`` triggers before the call reaches the
bridge. Override the ceiling at process start with ``RHINO_MCP_MAX_OBJECT_IDS``.
"""


# Pagination defaults applied across listing/extraction tools.
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500


def paginate(
    rows: list[Any],
    cursor: int = 0,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> tuple[list[Any], int | None]:
    """Slice ``rows`` into a single page.

    Returns ``(page, next_cursor)``. ``next_cursor`` is ``None`` when the
    page exhausts the input. ``cursor`` is clamped to ``[0, len(rows)]``,
    ``limit`` is clamped to ``[1, MAX_PAGE_LIMIT]``.
    """
    n = len(rows)
    start = max(0, min(int(cursor or 0), n))
    page_limit = max(1, min(int(limit or DEFAULT_PAGE_LIMIT), MAX_PAGE_LIMIT))
    end = min(start + page_limit, n)
    nxt = end if end < n else None
    return rows[start:end], nxt


def bridge_call_batch(
    steps: list[dict[str, Any]],
    *,
    on_error: str = "stop",
) -> dict[str, Any]:
    """Execute multiple bridge methods in a single round-trip.

    ``steps`` is a list of ``{"method": str, "params": dict}`` entries; the
    bridge dispatches each on the Rhino UI thread sequentially and returns
    a result envelope ``{"summary": {...}, "results": [...]}`` where each
    result entry mirrors the step's status (``"ok"`` | ``"error"``).
    """
    return runtime().require_bridge().call(
        "rhino.batch.execute",
        {"steps": steps, "on_error": on_error},
    )


def bridge_call(method: str, args: dict[str, Any]) -> dict[str, Any]:
    """Invoke a bridge JSON-RPC method with input/output debug logging.

    Wraps ``runtime().require_bridge().call(method, args)`` so every bridge
    tool emits a uniform ``→ method args=...`` / ``← method result_keys=...``
    pair at DEBUG level. ``RHINO_MCP_LOG_LEVEL=DEBUG`` activates the trace
    without changing tool semantics.

    On a connection-category ToolError the client is discarded and one
    lazy re-detection attempt is made before re-raising.
    """
    from rhino_mcp.utils.error_handling import ToolError

    _tool_log.debug("→ %s args=%s", method, args)
    rt = runtime()
    try:
        result = rt.require_bridge().call(method, args)
    except ToolError as exc:
        if exc.category.value != "connection":
            raise
        # Drop the dead client so require_bridge() will re-detect on next call.
        if rt.bridge is not None:
            try:
                rt.bridge.close()
            except Exception:
                pass
            rt.bridge = None
            rt.mode = Mode.STANDALONE
        result = rt.require_bridge().call(method, args)
    if isinstance(result, dict):
        _tool_log.debug("← %s result_keys=%s", method, list(result.keys()))
    else:
        _tool_log.debug("← %s result_type=%s", method, type(result).__name__)
    return result


async def bridge_call_async(method: str, args: dict[str, Any]) -> dict[str, Any]:
    """Asynchronous variant of :func:`bridge_call`.

    Uses ``BridgeClient.async_call`` so concurrent tool invocations don't
    block FastMCP's event loop. The bridge plugin still serialises calls
    onto Rhino's UI thread, so concurrency is bounded server-side; this
    only avoids stalling the MCP transport while waiting on Rhino.
    """
    _tool_log.debug("→ async %s args=%s", method, args)
    result = await runtime().require_bridge().async_call(method, args)
    if isinstance(result, dict):
        _tool_log.debug("← async %s result_keys=%s", method, list(result.keys()))
    else:
        _tool_log.debug("← async %s result_type=%s", method, type(result).__name__)
    return result


def to_point(p: Point3dModel) -> r3.Point3d:
    return r3.Point3d(p.x, p.y, p.z)


def to_vector(v: Vector3dModel) -> r3.Vector3d:
    return r3.Vector3d(v.x, v.y, v.z)


def doc(doc_id: str = "active") -> DocumentHandle:
    return registry().get_or_create(doc_id)


def add_object_with_attrs(
    handle: DocumentHandle,
    method: str,
    geometry: Any,
    layer: str | None = None,
    name: str | None = None,
    color: tuple[int, int, int, int] | None = None,
) -> str:
    """Add ``geometry`` to ``handle`` via ``handle.file3dm.Objects.<method>(geometry, attrs)``.

    ``method`` is the typed shortcut (``AddBrep``, ``AddCurve``, ``AddPolyline``, …).
    Some shortcuts (``AddTextDot``, ``AddLine``) take separate args rather than
    ``(geometry, attrs)``, so we fall back to the generic ``Add(geometry, attrs)``
    when the typed call signature does not accept geometry+attrs.
    """
    attrs = r3.ObjectAttributes()
    if layer is not None:
        attrs.LayerIndex = _resolve_layer_index(handle, layer)
    if name is not None:
        attrs.Name = name
    if color is not None:
        attrs.ObjectColor = color
        attrs.ColorSource = r3.ObjectColorSource.ColorFromObject
    add = getattr(handle.file3dm.Objects, method)
    try:
        gid: UUID = add(geometry, attrs)
    except TypeError:
        # rhino3dm typed-add overloads don't all accept (geometry, attrs);
        # fall through to the generic Add which accepts any GeometryBase.
        gid = handle.file3dm.Objects.Add(geometry, attrs)
    return handle.add_index(gid)


def _resolve_layer_index(handle: DocumentHandle, layer_name: str) -> int:
    """Return the layer index for ``layer_name``, creating the layer if absent."""
    idx = find_layer_index(handle, layer_name)
    if idx is not None:
        return idx
    layer = r3.Layer()
    layer.Name = layer_name
    return handle.file3dm.Layers.Add(layer)


def find_layer_index(handle: DocumentHandle, name: str) -> int | None:
    """Return the layer index for ``name`` or ``None`` if it does not exist."""
    for i in range(len(handle.file3dm.Layers)):
        if handle.file3dm.Layers[i].Name == name:
            return i
    return None


def find_material_index(handle: DocumentHandle, name: str) -> int | None:
    """Return the material index for ``name`` or ``None`` if it does not exist."""
    for i in range(len(handle.file3dm.Materials)):
        if handle.file3dm.Materials[i].Name == name:
            return i
    return None


def require_standalone_or_bridge() -> None:
    """No-op; placeholder for tools that work in both modes."""
    return


def require_bridge_only(tool_name: str) -> None:
    if runtime().mode is Mode.STANDALONE:
        raise unsupported_in_standalone(tool_name)


def object_summary(handle: DocumentHandle, gid: str, kind: str) -> dict[str, Any]:
    """Return the canonical structured response for ``add_*`` tools."""
    obj = handle.file3dm.Objects.FindId(gid)
    bb = obj.Geometry.GetBoundingBox() if obj is not None else None
    return {
        "doc_id": handle.doc_id,
        "object_id": gid,
        "kind": kind,
        "bounding_box": bbox_to_dict(bb) if bb is not None else None,
    }


def text_for(label: str, gid: str) -> str:
    return f"{label} created with id {gid}"
