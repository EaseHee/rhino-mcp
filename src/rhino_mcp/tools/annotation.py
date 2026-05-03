"""Annotation tools (text dots, dimensions, leaders, hatches, clipping planes).

rhino3dm exposes the data classes (Text, TextDot, DimLinear, etc.), so we can
add them in standalone mode. Bridge mode delegates so that styling and
auto-update behaviour follow Rhino's annotation system.

v0.3 adds drawing-set markup primitives — north arrow, scale bar, revision
cloud, callout, dimension style — so the LLM can finish a drawing without
dropping into rhino_execute_python.
"""

from __future__ import annotations

import itertools
import math
from typing import Annotated, Any
from uuid import UUID

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import PlaneModel, Point3dModel
from rhino_mcp.tools._helpers import (
    add_object_with_attrs,
    bridge_call,
    doc,
    object_summary,
    require_bridge_only,
    text_for,
    to_point,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )
    layer: str | None = Field(None)
    name: str | None = Field(None)


class _TextDotIn(_DocArg):
    text: str = Field(..., min_length=1)
    location: Point3dModel


class _TextIn(_DocArg):
    text: str = Field(..., min_length=1)
    location: Point3dModel
    height: Annotated[float, Field(gt=0)] = 1.0


class _LinearDimIn(_DocArg):
    point_a: Point3dModel
    point_b: Point3dModel
    plane: PlaneModel | None = None


class _AngularDimIn(_DocArg):
    center: Point3dModel
    point_a: Point3dModel
    point_b: Point3dModel


class _LeaderIn(_DocArg):
    points: list[Point3dModel] = Field(..., min_length=2)
    text: str = Field("")


class _HatchIn(_DocArg):
    boundary_curve_ids: list[str] = Field(..., min_length=1)
    pattern: str = Field("Solid")


class _ClipPlaneIn(_DocArg):
    plane: PlaneModel


class _NorthArrowIn(_DocArg):
    location: Point3dModel
    size: Annotated[float, Field(gt=0, le=10000)] = 20.0
    angle_deg: float = Field(
        0.0, description="Bearing of north relative to world +Y, clockwise."
    )
    style: str = Field("simple", description="'simple' (triangle + N) or 'compass' (4 cardinal lines).")


class _ScaleBarIn(_DocArg):
    location: Point3dModel
    total_length: Annotated[float, Field(gt=0, le=10000)] = 50.0
    divisions: Annotated[int, Field(ge=1, le=20)] = 5
    scale_denominator: Annotated[int, Field(ge=1, le=10000)] = 100
    label_height: Annotated[float, Field(gt=0)] = 2.5


class _RevisionCloudIn(_DocArg):
    boundary_points: list[Point3dModel] = Field(..., min_length=3)
    revision_no: str = Field("R1", min_length=1)
    date_iso: str = Field("")
    bump_count: Annotated[int, Field(ge=4, le=128)] = 24
    bump_radius: Annotated[float, Field(gt=0)] = 1.5


class _CalloutIn(_DocArg):
    target_point: Point3dModel
    leader_origin: Point3dModel
    text: str = Field(..., min_length=1)
    style: str = Field("balloon", description="'balloon' (circle + leader) or 'box' (rectangle + leader).")


class _DimensionStyleIn(BaseModel):
    name: str = Field(..., min_length=1)
    font: str = Field("Arial")
    text_height: Annotated[float, Field(gt=0)] = 2.5
    arrow_size: Annotated[float, Field(gt=0)] = 2.0
    color: tuple[int, int, int] = Field((0, 0, 0))


def _add_polyline(handle: Any, points: list[r3.Point3d], *, layer: str | None, name: str | None) -> str:
    poly = r3.Polyline()
    for p in points:
        poly.Add(p.X, p.Y, p.Z)
    pc = poly.ToPolylineCurve()
    attrs = r3.ObjectAttributes()
    if layer is not None:
        from rhino_mcp.tools._helpers import _resolve_layer_index

        attrs.LayerIndex = _resolve_layer_index(handle, layer)
    if name is not None:
        attrs.Name = name
    new_id: UUID = handle.file3dm.Objects.Add(pc, attrs)
    return handle.add_index(new_id)


def _add_circle(handle: Any, center: r3.Point3d, radius: float, *, layer: str | None, name: str | None) -> str:
    circle = r3.Circle(center, radius)
    nc = circle.ToNurbsCurve()
    attrs = r3.ObjectAttributes()
    if layer is not None:
        from rhino_mcp.tools._helpers import _resolve_layer_index

        attrs.LayerIndex = _resolve_layer_index(handle, layer)
    if name is not None:
        attrs.Name = name
    new_id: UUID = handle.file3dm.Objects.Add(nc, attrs)
    return handle.add_index(new_id)


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Add Text Dot", "readOnlyHint": False})
    def rhino_text_dot(args: _TextDotIn) -> dict[str, Any]:
        """Add a small label that always faces the camera in Rhino."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.annotation.text_dot", args.model_dump())
        h = doc(args.doc_id)
        td = r3.TextDot(args.text, to_point(args.location))
        gid = add_object_with_attrs(h, "AddTextDot", td, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "TextDot"), "text": text_for("TextDot", gid)}

    @mcp.tool(annotations={"title": "Add Text Annotation", "readOnlyHint": False})
    def rhino_text(args: _TextIn) -> dict[str, Any]:
        """Add 3D text annotation. Bridge mode honours the active dim style; standalone uses text-dot fallback."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.annotation.text", args.model_dump())
        # rhino3dm Text construction is read-only via OpenNURBS; emulate as text dot.
        h = doc(args.doc_id)
        td = r3.TextDot(args.text, to_point(args.location))
        gid = add_object_with_attrs(h, "AddTextDot", td, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Text"), "text": text_for("Text(dot)", gid)}

    @mcp.tool(annotations={"title": "Add North Arrow", "readOnlyHint": False})
    def rhino_annotation_north_arrow(args: _NorthArrowIn) -> dict[str, Any]:
        """Draw a north arrow centred on ``location``.

        ``angle_deg`` rotates the arrow clockwise from world +Y so callers can
        adapt to a site whose true north differs from grid north.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.annotation.north_arrow", args.model_dump())
        h = doc(args.doc_id)
        origin = to_point(args.location)
        angle = math.radians(90.0 - args.angle_deg)
        size = args.size
        ids: list[str] = []
        if args.style == "compass":
            for offset_deg in (0, 90, 180, 270):
                a = math.radians(90.0 - args.angle_deg + offset_deg)
                tip = r3.Point3d(origin.X + size * math.cos(a), origin.Y + size * math.sin(a), origin.Z)
                ids.append(_add_polyline(h, [origin, tip], layer=args.layer, name=f"compass_{offset_deg}"))
        else:
            tip = r3.Point3d(origin.X + size * math.cos(angle), origin.Y + size * math.sin(angle), origin.Z)
            half = size * 0.25
            sa = math.radians(90.0 - args.angle_deg + 150.0)
            sb = math.radians(90.0 - args.angle_deg - 150.0)
            bl = r3.Point3d(origin.X + half * math.cos(sa), origin.Y + half * math.sin(sa), origin.Z)
            br = r3.Point3d(origin.X + half * math.cos(sb), origin.Y + half * math.sin(sb), origin.Z)
            ids.append(
                _add_polyline(h, [tip, bl, origin, br, tip], layer=args.layer, name=args.name or "north_arrow")
            )
        td = r3.TextDot("N", r3.Point3d(origin.X, origin.Y - size * 0.4, origin.Z))
        attrs = r3.ObjectAttributes()
        if args.layer is not None:
            from rhino_mcp.tools._helpers import _resolve_layer_index

            attrs.LayerIndex = _resolve_layer_index(h, args.layer)
        attrs.Name = "north_arrow_label"
        new_id = h.file3dm.Objects.Add(td, attrs)
        ids.append(h.add_index(new_id))
        return {
            "summary": {"object_ids": ids, "style": args.style, "angle_deg": args.angle_deg, "size": args.size},
            "text": f"North arrow placed ({args.style}) with {len(ids)} object(s)",
        }

    @mcp.tool(annotations={"title": "Add Scale Bar", "readOnlyHint": False})
    def rhino_annotation_scale_bar(args: _ScaleBarIn) -> dict[str, Any]:
        """Draw a divided scale bar with a label.

        Bar is drawn in document units; the label reports the represented
        real-world distance based on ``scale_denominator``.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.annotation.scale_bar", args.model_dump())
        h = doc(args.doc_id)
        origin = to_point(args.location)
        seg = args.total_length / args.divisions
        bar_h = max(args.label_height, args.total_length * 0.05)
        ids: list[str] = []
        for i in range(args.divisions):
            x0 = origin.X + i * seg
            x1 = origin.X + (i + 1) * seg
            rect = [
                r3.Point3d(x0, origin.Y, origin.Z),
                r3.Point3d(x1, origin.Y, origin.Z),
                r3.Point3d(x1, origin.Y + bar_h, origin.Z),
                r3.Point3d(x0, origin.Y + bar_h, origin.Z),
                r3.Point3d(x0, origin.Y, origin.Z),
            ]
            ids.append(_add_polyline(h, rect, layer=args.layer, name=f"scale_bar_{i}"))
        real_m = (args.total_length / 1000.0) * args.scale_denominator
        td = r3.TextDot(
            f"0 .. {real_m:.1f} m  (1:{args.scale_denominator})",
            r3.Point3d(origin.X, origin.Y - bar_h, origin.Z),
        )
        attrs = r3.ObjectAttributes()
        if args.layer is not None:
            from rhino_mcp.tools._helpers import _resolve_layer_index

            attrs.LayerIndex = _resolve_layer_index(h, args.layer)
        attrs.Name = "scale_bar_label"
        new_id = h.file3dm.Objects.Add(td, attrs)
        ids.append(h.add_index(new_id))
        return {
            "summary": {"object_ids": ids, "divisions": args.divisions, "scale_denominator": args.scale_denominator},
            "text": f"Scale bar placed ({args.divisions} division(s) @1:{args.scale_denominator})",
        }

    @mcp.tool(annotations={"title": "Add Revision Cloud", "readOnlyHint": False})
    def rhino_annotation_revision_cloud(args: _RevisionCloudIn) -> dict[str, Any]:
        """Draw a revision cloud (bumpy polyline) around a region of interest with a revision label."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.annotation.revision_cloud", args.model_dump())
        h = doc(args.doc_id)
        pts = [to_point(p) for p in args.boundary_points]
        if pts[0].DistanceTo(pts[-1]) > 1e-6:
            pts.append(pts[0])
        # Sample uniformly along boundary perimeter and emit small arcs.
        cloud_pts: list[r3.Point3d] = []
        per_seg = max(1, args.bump_count // (len(pts) - 1))
        for a, b in itertools.pairwise(pts):
            for k in range(per_seg):
                t = k / per_seg
                base = r3.Point3d(
                    a.X * (1 - t) + b.X * t,
                    a.Y * (1 - t) + b.Y * t,
                    a.Z * (1 - t) + b.Z * t,
                )
                # Bump outward perpendicular to (b-a) in XY.
                dx = b.X - a.X
                dy = b.Y - a.Y
                ln = math.hypot(dx, dy) or 1.0
                nx, ny = -dy / ln, dx / ln
                bump = r3.Point3d(
                    base.X + nx * args.bump_radius,
                    base.Y + ny * args.bump_radius,
                    base.Z,
                )
                cloud_pts.append(base)
                cloud_pts.append(bump)
        cloud_pts.append(pts[0])
        ids = [_add_polyline(h, cloud_pts, layer=args.layer, name=args.name or "revision_cloud")]
        # Label.
        cx = sum(p.X for p in pts) / len(pts)
        cy = sum(p.Y for p in pts) / len(pts)
        cz = sum(p.Z for p in pts) / len(pts)
        label = f"Rev {args.revision_no}"
        if args.date_iso:
            label += f"  {args.date_iso}"
        td = r3.TextDot(label, r3.Point3d(cx, cy, cz))
        attrs = r3.ObjectAttributes()
        if args.layer is not None:
            from rhino_mcp.tools._helpers import _resolve_layer_index

            attrs.LayerIndex = _resolve_layer_index(h, args.layer)
        attrs.Name = f"revision_label_{args.revision_no}"
        new_id = h.file3dm.Objects.Add(td, attrs)
        ids.append(h.add_index(new_id))
        return {
            "summary": {"object_ids": ids, "revision_no": args.revision_no, "vertex_count": len(cloud_pts)},
            "text": f"Revision cloud {args.revision_no} placed",
        }

    @mcp.tool(annotations={"title": "Add Callout", "readOnlyHint": False})
    def rhino_annotation_callout(args: _CalloutIn) -> dict[str, Any]:
        """Add a callout (leader + balloon or boxed label)."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.annotation.callout", args.model_dump())
        h = doc(args.doc_id)
        target = to_point(args.target_point)
        origin = to_point(args.leader_origin)
        ids: list[str] = []
        ids.append(_add_polyline(h, [target, origin], layer=args.layer, name="callout_leader"))
        if args.style == "box":
            tw = max(len(args.text) * 1.5, 6.0)
            th = 4.0
            box = [
                r3.Point3d(origin.X, origin.Y, origin.Z),
                r3.Point3d(origin.X + tw, origin.Y, origin.Z),
                r3.Point3d(origin.X + tw, origin.Y + th, origin.Z),
                r3.Point3d(origin.X, origin.Y + th, origin.Z),
                r3.Point3d(origin.X, origin.Y, origin.Z),
            ]
            ids.append(_add_polyline(h, box, layer=args.layer, name="callout_box"))
        else:  # balloon
            ids.append(_add_circle(h, origin, 4.0, layer=args.layer, name="callout_balloon"))
        td = r3.TextDot(args.text, origin)
        attrs = r3.ObjectAttributes()
        if args.layer is not None:
            from rhino_mcp.tools._helpers import _resolve_layer_index

            attrs.LayerIndex = _resolve_layer_index(h, args.layer)
        attrs.Name = args.name or "callout_text"
        new_id = h.file3dm.Objects.Add(td, attrs)
        ids.append(h.add_index(new_id))
        return {
            "summary": {"object_ids": ids, "style": args.style, "text": args.text},
            "text": f"Callout placed ({args.style})",
        }

    if mode is Mode.STANDALONE:
        return  # bridge-only annotation tools below

    @mcp.tool(annotations={"title": "Linear Dimension", "readOnlyHint": False})
    def rhino_dimension_linear(args: _LinearDimIn) -> dict[str, Any]:
        """Add a linear dimension between two points."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dimension_linear")
        return runtime().require_bridge().call("rhino.annotation.dim_linear", args.model_dump())

    @mcp.tool(annotations={"title": "Aligned Dimension", "readOnlyHint": False})
    def rhino_dimension_aligned(args: _LinearDimIn) -> dict[str, Any]:
        """Add an aligned dimension between two points."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dimension_aligned")
        return runtime().require_bridge().call("rhino.annotation.dim_aligned", args.model_dump())

    @mcp.tool(annotations={"title": "Angular Dimension", "readOnlyHint": False})
    def rhino_dimension_angular(args: _AngularDimIn) -> dict[str, Any]:
        """Add an angular dimension at a vertex."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dimension_angular")
        return runtime().require_bridge().call("rhino.annotation.dim_angular", args.model_dump())

    @mcp.tool(annotations={"title": "Add Leader", "readOnlyHint": False})
    def rhino_leader(args: _LeaderIn) -> dict[str, Any]:
        """Add a multi-point leader (with optional text)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_leader")
        return runtime().require_bridge().call("rhino.annotation.leader", args.model_dump())

    @mcp.tool(annotations={"title": "Add Hatch", "readOnlyHint": False})
    def rhino_hatch(args: _HatchIn) -> dict[str, Any]:
        """Add a hatch over the given closed curves."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_hatch")
        return runtime().require_bridge().call("rhino.annotation.hatch", args.model_dump())

    @mcp.tool(annotations={"title": "Clipping Plane", "readOnlyHint": False})
    def rhino_clipping_plane(args: _ClipPlaneIn) -> dict[str, Any]:
        """Add a clipping plane to all viewports."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_clipping_plane")
        return runtime().require_bridge().call("rhino.annotation.clipping_plane", args.model_dump())

    @mcp.tool(annotations={"title": "Create Dimension Style", "readOnlyHint": False})
    def rhino_annotation_dimension_style(args: _DimensionStyleIn) -> dict[str, Any]:
        """Register a reusable dimension style (bridge only — Rhino DimStyle table)."""
        require_bridge_only("rhino_annotation_dimension_style")
        return bridge_call("rhino.annotation.dim_style_create", args.model_dump())
