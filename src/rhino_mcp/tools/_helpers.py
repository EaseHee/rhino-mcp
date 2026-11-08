"""Tool-implementation helpers used across modules."""

from __future__ import annotations

import base64
import functools
import itertools
import math
import os
from collections import Counter
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID

import rhino3dm as r3
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.utilities.types import Image
from pydantic import BaseModel, Field

from rhino_mcp.document import DocumentHandle, registry
from rhino_mcp.models.geometry_types import Point3dModel, Vector3dModel
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import ErrorCategory, ToolError, unsupported_in_standalone
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode
from rhino_mcp.utils.serialization import bbox_to_dict

if TYPE_CHECKING:
    from rhino_mcp.bridge.rhino_connection import ProgressCallback

_tool_log = get_logger("tool")

ToolContext = Context[Any, Any, Any]
"""FastMCP request context; annotate a tool's ``ctx: ToolContext | None = None`` to receive it.

FastMCP injects it by type and keeps it out of the tool's input schema.
"""


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


def _client_call(
    client: Any,
    method: str,
    args: dict[str, Any],
    on_progress: ProgressCallback | None,
) -> dict[str, Any]:
    # Pass the hook only when set so duck-typed test clients keep working.
    if on_progress is None:
        result: dict[str, Any] = client.call(method, args)
    else:
        result = client.call(method, args, on_progress=on_progress)
    return result


def bridge_call_batch(
    steps: list[dict[str, Any]],
    *,
    on_error: str = "stop",
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Execute multiple bridge methods in a single round-trip.

    ``steps`` is a list of ``{"method": str, "params": dict}`` entries; the
    bridge dispatches each on the Rhino UI thread sequentially and returns
    a result envelope ``{"summary": {...}, "results": [...]}`` where each
    result entry mirrors the step's status (``"ok"`` | ``"error"``).
    """
    return _client_call(
        runtime().require_bridge(),
        "rhino.batch.execute",
        {"steps": steps, "on_error": on_error},
        on_progress,
    )


def bridge_call(
    method: str,
    args: dict[str, Any],
    *,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Invoke a bridge JSON-RPC method with input/output debug logging.

    Wraps ``runtime().require_bridge().call(method, args)`` so every bridge
    tool emits a uniform ``→ method args=...`` / ``← method result_keys=...``
    pair at DEBUG level. ``RHINO_MCP_LOG_LEVEL=DEBUG`` activates the trace
    without changing tool semantics.

    On a connection-category ToolError the client is discarded and one
    lazy re-detection attempt is made before re-raising.

    ``on_progress(progress, total, message)`` receives the bridge's
    ``rhino.progress`` notifications on the calling thread.
    """
    from rhino_mcp.utils.error_handling import ToolError

    _tool_log.debug("→ %s args=%s", method, args)
    rt = runtime()
    try:
        result = _client_call(rt.require_bridge(), method, args, on_progress)
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
        result = _client_call(rt.require_bridge(), method, args, on_progress)
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


def _has_progress_token(ctx: ToolContext | None) -> bool:
    """True when the client asked for progress (request carries a ``progressToken``)."""
    if ctx is None:
        return False
    try:
        meta = ctx.request_context.meta
    except (LookupError, ValueError):
        return False
    return meta is not None and getattr(meta, "progressToken", None) is not None


_PROGRESS_DONE = object()


async def run_with_progress(ctx: ToolContext | None, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a blocking bridge helper on a worker thread with progress forwarding.

    ``fn`` must accept an ``on_progress`` keyword (``bridge_call``,
    ``bridge_call_batch``). FastMCP 1.27 runs sync tools directly on the
    event loop, so the bridge call is moved to a worker thread to keep the
    loop free for ``notifications/progress``.

    The worker never waits on the loop: ``BridgeClient`` invokes the hook
    while holding its request lock, and a sync tool blocked on that lock
    from the loop would otherwise deadlock with a hook blocked on the loop.
    Frames are queued with ``call_soon_threadsafe`` and a single drainer
    task sends them in order; the drainer is awaited before returning so no
    notification trails the tool result.
    """
    import asyncio

    import anyio.to_thread

    if not _has_progress_token(ctx):
        return await anyio.to_thread.run_sync(functools.partial(fn, *args, on_progress=None, **kwargs))
    assert ctx is not None

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    last = 0.0

    async def _drain() -> None:
        import math

        sent: float | None = None
        while True:
            item = await queue.get()
            if item is _PROGRESS_DONE:
                return
            progress, total, message = item
            # MCP requires progress to increase with every notification.
            if sent is not None and progress <= sent:
                progress = math.nextafter(sent, math.inf)
            if total is not None and progress > total:
                total = progress
            sent = progress
            try:
                await ctx.report_progress(progress, total, message)
            except Exception as exc:
                _tool_log.debug("report_progress failed: %s", exc)

    def _forward(progress: float | None, total: float | None, message: str | None) -> None:
        nonlocal last
        # MCP requires a numeric progress; message-only frames reuse the last value.
        if progress is not None:
            last = progress
        loop.call_soon_threadsafe(queue.put_nowait, (last, total, message))

    drainer = asyncio.create_task(_drain())
    try:
        return await anyio.to_thread.run_sync(functools.partial(fn, *args, on_progress=_forward, **kwargs))
    finally:
        queue.put_nowait(_PROGRESS_DONE)
        await drainer


async def bridge_call_with_progress(
    method: str,
    args: dict[str, Any],
    ctx: ToolContext | None,
) -> dict[str, Any]:
    """:func:`bridge_call` off the event loop, streaming progress to ``ctx``."""
    result: dict[str, Any] = await run_with_progress(ctx, bridge_call, method, args)
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
    """Return the layer index for ``layer_name``, creating the layer if absent.

    rhino3dm normalises names on ``Layers.Add`` (strips surrounding whitespace,
    suffixes duplicates with `` 02``), so the lookup uses the stripped name;
    otherwise every call with a padded name would add yet another layer.
    """
    from rhino_mcp.utils.error_handling import parameter_error

    name = (layer_name or "").strip()
    if not name:
        raise parameter_error("layer", "layer name must not be empty")
    idx = find_layer_index(handle, name)
    if idx is not None:
        return idx
    layer = r3.Layer()
    layer.Name = name
    new_idx = handle.file3dm.Layers.Add(layer)
    if not isinstance(new_idx, int) or new_idx < 0:
        raise RuntimeError(f"rhino3dm refused to add layer {name!r}")
    return new_idx


def find_layer_index(handle: DocumentHandle, name: str) -> int | None:
    """Return the layer index for ``name`` or ``None`` if it does not exist.

    Scans the table by name instead of ``Layers.FindName`` / ``FindIndex``:
    since rhino3dm 8.32 those return ``None`` (FindName/FindId) or raise
    ``IndexError`` (FindIndex) on a miss, and FindName only matches one parent.
    """
    layers = handle.file3dm.Layers
    for i in range(len(layers)):
        try:
            layer = layers[i]
        except (IndexError, RuntimeError):
            continue
        if layer is not None and layer.Name == name:
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


# --- Curve arc length (shared by schedule / query / geometry validation)

# 5-point Gauss-Legendre nodes/weights on [-1, 1].
_GL_NODES = (
    (0.0, 0.5688888888888889),
    (-0.5384693101056831, 0.47862867049936647),
    (0.5384693101056831, 0.47862867049936647),
    (-0.9061798459386640, 0.23692688505618908),
    (0.9061798459386640, 0.23692688505618908),
)


def curve_length(curve: Any, subdivisions: int = 8) -> float:
    """Arc length of a rhino3dm curve by Gauss-Legendre quadrature per NURBS span.

    rhino3dm has no ``Curve.GetLength``, so the speed ``|C'(t)|`` from
    ``DerivativeAt(t, 1)`` (a ``[point, first_derivative]`` list since 8.32)
    is integrated over each knot span. Degree-1 spans are straight segments,
    so their length is the endpoint distance. Higher degrees use
    ``degree + 1`` sub-intervals per span (capped at ``subdivisions``), which
    keeps the relative error below 1e-10 for degrees 2-5.
    """
    nurbs: Any = curve if isinstance(curve, r3.NurbsCurve) else curve.ToNurbsCurve()
    if nurbs is None:
        return 0.0
    t0, t1 = nurbs.Domain.T0, nurbs.Domain.T1
    knots = nurbs.Knots
    breaks = sorted({t0, t1, *(k for k in (knots[i] for i in range(len(knots))) if t0 < k < t1)})
    degree = int(nurbs.Degree)
    if degree <= 1:
        points = [nurbs.PointAt(t) for t in breaks]
        return float(sum(p.DistanceTo(q) for p, q in itertools.pairwise(points)))
    pieces = max(1, min(subdivisions, degree + 1))
    total = 0.0
    for a, b in itertools.pairwise(breaks):
        step = (b - a) / pieces
        for s in range(pieces):
            lo = a + s * step
            half = 0.5 * step
            mid = lo + half
            for x, w in _GL_NODES:
                d1 = nurbs.DerivativeAt(mid + half * x, 1)[1]
                total += w * half * math.sqrt(d1.X * d1.X + d1.Y * d1.Y + d1.Z * d1.Z)
    return total


# --- SubD summary (shared by subd / query)


def _iterate(iterator: Any) -> list[Any]:
    """Drain a rhino3dm SubD component iterator into a list.

    The iterators expose ``Count`` / ``First()`` / ``Next()`` only (no
    ``__iter__``); ``First()`` returns a component even when ``Count`` is 0,
    so the loop is bounded by ``Count``.
    """
    count = int(iterator.Count)
    if count <= 0:
        return []
    items = [iterator.First()]
    for _ in range(count - 1):
        items.append(iterator.Next())
    return [c for c in items if c is not None]


def _tag_name(tag: Any) -> str:
    return getattr(tag, "name", str(tag))


def subd_summary(subd: Any, *, include_creases: bool = False, limit: int = 200) -> dict[str, Any]:
    """Return topology counts, tag histograms, and crease info for a rhino3dm SubD."""
    vertices = _iterate(subd.Vertices)
    edges = _iterate(subd.Edges)
    faces = _iterate(subd.Faces)

    vertex_tags = Counter(_tag_name(v.Tag) for v in vertices)
    edge_tags = Counter(_tag_name(e.Tag) for e in edges)
    face_sides = Counter(int(f.EdgeCount) for f in faces)
    # An edge with one adjacent face is a boundary edge (open SubD).
    boundary_edges = sum(1 for e in edges if int(e.FaceCount) == 1)
    crease_edges = [e for e in edges if e.IsCrease]
    sharp_edges = [e for e in edges if e.IsSharp]
    max_sharpness = 0.0
    for e in sharp_edges:
        max_sharpness = max(max_sharpness, float(e.EndSharpness(0)), float(e.EndSharpness(1)))

    summary: dict[str, Any] = {
        "vertex_count": int(subd.VertexCount),
        "edge_count": int(subd.EdgeCount),
        "face_count": int(subd.FaceCount),
        "is_solid": bool(subd.IsSolid),
        "vertex_tags": dict(sorted(vertex_tags.items())),
        "edge_tags": dict(sorted(edge_tags.items())),
        "face_side_counts": {str(k): v for k, v in sorted(face_sides.items())},
        "boundary_edge_count": boundary_edges,
        "crease_edge_count": len(crease_edges),
        "sharp_edge_count": len(sharp_edges),
        "max_edge_sharpness": max_sharpness,
        "corner_vertex_count": sum(1 for v in vertices if v.IsCorner),
        "dart_vertex_count": sum(1 for v in vertices if v.IsDart),
    }
    if include_creases:
        summary["creases"] = [
            {
                "edge_id": int(e.Id),
                "tag": _tag_name(e.Tag),
                "is_sharp": bool(e.IsSharp),
                "end_sharpness": [float(e.EndSharpness(0)), float(e.EndSharpness(1))],
            }
            for e in (crease_edges + [e for e in sharp_edges if not e.IsCrease])[:limit]
        ]
        summary["corners"] = [
            {"vertex_id": int(v.Id), "point": _pt(v.ControlNetPoint)}
            for v in vertices
            if v.IsCorner
        ][:limit]
    return summary


def _pt(p: Any) -> dict[str, float]:
    return {"x": float(p.X), "y": float(p.Y), "z": float(p.Z)}


# --- Viewport capture content (shared by io / display)

# Return type of capture tools: inline image + summary, or summary only.
CaptureResult = list[Image | dict[str, Any]] | dict[str, Any]


class CaptureImageArgs(BaseModel):
    """Inline-image controls shared by every viewport capture tool."""

    include_image: bool = Field(
        True,
        description=(
            "Return the capture as MCP image content so the model can see it. "
            "Set False (with a file path) to get only the summary and save tokens."
        ),
    )
    max_width: Annotated[int, Field(ge=0, le=8192)] = Field(
        1024,
        description=(
            "Downscale the inline image to at most this width (aspect ratio kept); "
            "0 = native capture size. The file at the output path keeps full size."
        ),
    )
    format: Literal["jpeg", "png"] = Field(
        "jpeg", description="Encoding of the inline image (JPEG is far smaller)."
    )
    jpeg_quality: Annotated[int, Field(ge=1, le=100)] = Field(
        80, description="JPEG quality for the inline image (ignored for PNG)."
    )


_MIME_TO_FORMAT = {"image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg"}


def capture_params(args: BaseModel, include_image: bool) -> dict[str, Any]:
    """Build the bridge payload for a capture handler from a capture input model."""
    params = args.model_dump(exclude={"include_image", "mime"})
    params["as_base64"] = include_image
    return params


def capture_content(result: Any, include_image: bool) -> CaptureResult:
    """Turn a bridge capture response into ``[Image, summary]`` (or summary only).

    The bridge returns the encoded bytes as base64 in ``image_base64``; the
    string is decoded into MCP image content and stripped from the summary
    so the model never receives the payload as text tokens.
    """
    if not isinstance(result, dict):
        return {"result": result}
    encoded = result.pop("image_base64", None)
    summary = result.get("summary")
    if isinstance(summary, dict):
        encoded = summary.pop("image_base64", None) or encoded
    else:
        summary = {}
        result["summary"] = summary
    mime = str(result.pop("mime", None) or summary.get("mime") or "image/png")
    if not encoded:
        if not include_image:
            return result
        encode_error = result.get("base64_error")
        hint = (
            "Update the rhino-mcp plug-in in Rhino to the version matching this server "
            "(older plug-ins ignore as_base64/format and return only a file path); "
            "if it is current, check that a viewport is visible and retry."
        )
        raise ToolError(
            ErrorCategory.INTERNAL,
            "Viewport capture returned no image"
            + (f": {encode_error}. " if encode_error else ". ")
            + hint,
            hint,
            details={"base64_error": encode_error, "summary": summary},
        )
    data = base64.b64decode(encoded)
    summary["mime"] = mime
    summary["bytes"] = len(data)
    if not include_image:
        return result
    image = Image(data=data, format=_MIME_TO_FORMAT.get(mime, "png"))
    return [image, result]
