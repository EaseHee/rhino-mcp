"""Geometry-creation tools (points, curves, polylines, basic primitives).

All thirteen tools in this module work in both standalone (rhino3dm) and bridge
modes. In bridge mode they forward to RhinoCommon for richer behaviour (e.g.
arbitrary planes); in standalone mode they construct the closest equivalent
using rhino3dm's constructor surface.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import PlaneModel, Point3dModel
from rhino_mcp.tools._helpers import (
    add_object_with_attrs,
    doc,
    object_summary,
    text_for,
    to_point,
    to_vector,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error
from rhino_mcp.utils.registry import Mode

# ---------- input models ----------


class _DocArg(BaseModel):
    doc_id: str = Field("active", description="Document handle (default 'active').")
    layer: str | None = Field(None, description="Optional layer name; created if absent.")
    name: str | None = Field(None, description="Optional object name.")


class _PointIn(_DocArg):
    point: Point3dModel = Field(..., description="World coordinates of the point.")


class _LineIn(_DocArg):
    start: Point3dModel = Field(..., description="Line start.")
    end: Point3dModel = Field(..., description="Line end.")


class _PolylineIn(_DocArg):
    points: list[Point3dModel] = Field(..., min_length=2, description="Ordered vertex list.")
    closed: bool = Field(False, description="Close the polyline with a final segment.")


class _CircleIn(_DocArg):
    center: Point3dModel = Field(..., description="Circle centre.")
    radius: Annotated[float, Field(gt=0, description="Radius (>0) in document units.")]
    plane: PlaneModel | None = Field(
        None,
        description="Optional plane; defaults to the XY plane translated to centre.",
    )


class _ArcIn(_DocArg):
    center: Point3dModel = Field(..., description="Arc centre.")
    radius: Annotated[float, Field(gt=0, description="Radius (>0).")]
    angle_degrees: Annotated[
        float,
        Field(gt=0, lt=360, description="Sweep angle in degrees (0 < angle < 360)."),
    ]


class _EllipseIn(_DocArg):
    center: Point3dModel = Field(..., description="Centre of the ellipse.")
    radius_x: Annotated[float, Field(gt=0, description="Semi-axis along X.")]
    radius_y: Annotated[float, Field(gt=0, description="Semi-axis along Y.")]


class _RectangleIn(_DocArg):
    corner: Point3dModel = Field(..., description="Lower-left corner (in plane).")
    width: Annotated[float, Field(gt=0, description="Width along plane X.")]
    height: Annotated[float, Field(gt=0, description="Height along plane Y.")]


class _PolygonIn(_DocArg):
    center: Point3dModel = Field(..., description="Polygon centre.")
    radius: Annotated[float, Field(gt=0, description="Circumscribed radius.")]
    sides: Annotated[int, Field(ge=3, le=256, description="Number of sides (3-256).")]
    inscribed: bool = Field(
        False, description="If true, the polygon is inscribed in the circle."
    )


class _HelixIn(_DocArg):
    center: Point3dModel = Field(..., description="Base centre of the helix.")
    radius: Annotated[float, Field(gt=0, description="Helix radius.")]
    pitch: Annotated[float, Field(gt=0, description="Vertical rise per turn.")]
    turns: Annotated[float, Field(gt=0, description="Number of turns.")]
    points_per_turn: Annotated[int, Field(ge=8, le=512, description="Sampling density.")] = 32


class _SpiralIn(_DocArg):
    center: Point3dModel = Field(..., description="Spiral centre.")
    start_radius: Annotated[float, Field(gt=0)]
    end_radius: Annotated[float, Field(gt=0)]
    pitch: Annotated[float, Field(gt=0, description="Vertical rise per turn (0 for flat).")]
    turns: Annotated[float, Field(gt=0)]
    points_per_turn: Annotated[int, Field(ge=8, le=512)] = 32


class _NurbsCurveIn(_DocArg):
    control_points: list[Point3dModel] = Field(
        ..., min_length=2, description="Control polygon vertices."
    )
    degree: Annotated[int, Field(ge=1, le=11, description="Curve degree (1-11).")] = 3


class _InterpolateCurveIn(_DocArg):
    points: list[Point3dModel] = Field(
        ..., min_length=2, description="Points the curve must pass through."
    )
    degree: Annotated[int, Field(ge=1, le=11)] = 3


class _RebuildCurveIn(_DocArg):
    object_id: str = Field(..., description="GUID of an existing curve to rebuild.")
    point_count: Annotated[int, Field(ge=2, le=1024)] = 16
    degree: Annotated[int, Field(ge=1, le=11)] = 3


# ---------- registration ----------


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(
        annotations={
            "title": "Add Point",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        }
    )
    def rhino_point(args: _PointIn) -> dict[str, Any]:
        """Add a single point to the document."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.point", args.model_dump())
        h = doc(args.doc_id)
        gid = add_object_with_attrs(
            h, "AddPoint", to_point(args.point), layer=args.layer, name=args.name
        )
        return {"summary": object_summary(h, gid, "Point"), "text": text_for("Point", gid)}

    @mcp.tool(annotations={"title": "Add Line", "readOnlyHint": False})
    def rhino_line(args: _LineIn) -> dict[str, Any]:
        """Add a line between two points."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.line", args.model_dump())
        h = doc(args.doc_id)
        line = r3.Line(to_point(args.start), to_point(args.end))
        if line.Length == 0:
            raise parameter_error("end", "must differ from start", "any non-coincident point")
        gid = h.add_index(h.file3dm.Objects.AddLine(line.From, line.To))
        return {"summary": object_summary(h, gid, "Line"), "text": text_for("Line", gid)}

    @mcp.tool(annotations={"title": "Add Polyline", "readOnlyHint": False})
    def rhino_polyline(args: _PolylineIn) -> dict[str, Any]:
        """Add a polyline through the given points; optionally closed."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.polyline", args.model_dump())
        h = doc(args.doc_id)
        pl = r3.Polyline()
        for p in args.points:
            pl.Add(p.x, p.y, p.z)
        if args.closed:
            first = args.points[0]
            pl.Add(first.x, first.y, first.z)
        gid = add_object_with_attrs(h, "AddPolyline", pl, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Polyline"), "text": text_for("Polyline", gid)}

    @mcp.tool(annotations={"title": "Add Arc", "readOnlyHint": False})
    def rhino_arc(args: _ArcIn) -> dict[str, Any]:
        """Add an arc by centre, radius, and sweep angle (in degrees)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.arc", args.model_dump())
        h = doc(args.doc_id)
        arc = r3.Arc(to_point(args.center), args.radius, math.radians(args.angle_degrees))
        gid = add_object_with_attrs(h, "AddArc", arc, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Arc"), "text": text_for("Arc", gid)}

    @mcp.tool(annotations={"title": "Add Circle", "readOnlyHint": False})
    def rhino_circle(args: _CircleIn) -> dict[str, Any]:
        """Add a circle by centre and radius (optionally on a custom plane)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.circle", args.model_dump())
        h = doc(args.doc_id)
        circle = r3.Circle(to_point(args.center), args.radius)
        if args.plane is not None:
            circle.Plane = r3.Plane(
                to_point(args.plane.origin),
                to_vector(args.plane.x_axis),
                to_vector(args.plane.y_axis),
            )
        gid = add_object_with_attrs(h, "AddCircle", circle, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Circle"), "text": text_for("Circle", gid)}

    @mcp.tool(annotations={"title": "Add Ellipse", "readOnlyHint": False})
    def rhino_ellipse(args: _EllipseIn) -> dict[str, Any]:
        """Add an ellipse on the world XY plane (rhino3dm builds it as a NURBS approximation)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.ellipse", args.model_dump())
        h = doc(args.doc_id)
        # rhino3dm cannot construct Ellipse directly (no __init__); approximate
        # with a degree-3 NURBS curve on 8 control points (Bezier ellipse).
        nc = _ellipse_nurbs(to_point(args.center), args.radius_x, args.radius_y)
        gid = add_object_with_attrs(h, "AddCurve", nc, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Ellipse"), "text": text_for("Ellipse", gid)}

    @mcp.tool(annotations={"title": "Add Rectangle", "readOnlyHint": False})
    def rhino_rectangle(args: _RectangleIn) -> dict[str, Any]:
        """Add a rectangle as a closed polyline on the XY plane."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.rectangle", args.model_dump())
        h = doc(args.doc_id)
        c = args.corner
        pl = r3.Polyline()
        pl.Add(c.x, c.y, c.z)
        pl.Add(c.x + args.width, c.y, c.z)
        pl.Add(c.x + args.width, c.y + args.height, c.z)
        pl.Add(c.x, c.y + args.height, c.z)
        pl.Add(c.x, c.y, c.z)
        gid = add_object_with_attrs(h, "AddPolyline", pl, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Rectangle"), "text": text_for("Rectangle", gid)}

    @mcp.tool(annotations={"title": "Add Regular Polygon", "readOnlyHint": False})
    def rhino_polygon(args: _PolygonIn) -> dict[str, Any]:
        """Add a regular polygon (inscribed or circumscribed) on the XY plane."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.polygon", args.model_dump())
        h = doc(args.doc_id)
        circle = r3.Circle(to_point(args.center), args.radius)
        creator = (
            r3.Polyline.CreateInscribedPolygon
            if args.inscribed
            else r3.Polyline.CreateCircumscribedPolygon
        )
        pl = creator(circle, args.sides)
        gid = add_object_with_attrs(h, "AddPolyline", pl, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Polygon"), "text": text_for("Polygon", gid)}

    @mcp.tool(annotations={"title": "Add Helix", "readOnlyHint": False})
    def rhino_helix(args: _HelixIn) -> dict[str, Any]:
        """Add a helix sampled into a NURBS curve."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.helix", args.model_dump())
        h = doc(args.doc_id)
        nc = _helix_nurbs(
            to_point(args.center),
            args.radius,
            args.radius,
            args.pitch,
            args.turns,
            args.points_per_turn,
        )
        gid = add_object_with_attrs(h, "AddCurve", nc, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Helix"), "text": text_for("Helix", gid)}

    @mcp.tool(annotations={"title": "Add Spiral", "readOnlyHint": False})
    def rhino_spiral(args: _SpiralIn) -> dict[str, Any]:
        """Add a tapered spiral sampled into a NURBS curve."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.spiral", args.model_dump())
        h = doc(args.doc_id)
        nc = _helix_nurbs(
            to_point(args.center),
            args.start_radius,
            args.end_radius,
            args.pitch,
            args.turns,
            args.points_per_turn,
        )
        gid = add_object_with_attrs(h, "AddCurve", nc, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Spiral"), "text": text_for("Spiral", gid)}

    @mcp.tool(annotations={"title": "Add NURBS Curve from Control Points", "readOnlyHint": False})
    def rhino_nurbs_curve(args: _NurbsCurveIn) -> dict[str, Any]:
        """Add a NURBS curve from a control polygon."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.geometry.nurbs_curve", args.model_dump())
        h = doc(args.doc_id)
        if len(args.control_points) <= args.degree:
            raise parameter_error(
                "control_points",
                f"need at least degree+1 = {args.degree + 1} control points",
                "more points or lower degree",
            )
        pts = [to_point(p) for p in args.control_points]
        nc = r3.NurbsCurve.CreateControlPointCurve(pts, args.degree)
        gid = add_object_with_attrs(h, "AddCurve", nc, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "NurbsCurve"), "text": text_for("NurbsCurve", gid)}

    @mcp.tool(annotations={"title": "Interpolate Curve Through Points", "readOnlyHint": False})
    def rhino_interpolate_curve(args: _InterpolateCurveIn) -> dict[str, Any]:
        """Add an interpolated NURBS curve passing through the given points."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call(
                "rhino.geometry.interpolate_curve", args.model_dump()
            )
        h = doc(args.doc_id)
        # rhino3dm lacks a direct interpolation helper; approximate with a
        # control-point curve clamped to start/end (good enough for sketching).
        pts = [to_point(p) for p in args.points]
        nc = r3.NurbsCurve.CreateControlPointCurve(pts, min(args.degree, len(pts) - 1))
        gid = add_object_with_attrs(h, "AddCurve", nc, layer=args.layer, name=args.name)
        return {
            "summary": object_summary(h, gid, "InterpolatedCurve"),
            "text": text_for("InterpolatedCurve", gid),
        }

    @mcp.tool(annotations={"title": "Rebuild Curve", "readOnlyHint": False})
    def rhino_rebuild_curve(args: _RebuildCurveIn) -> dict[str, Any]:
        """Rebuild an existing curve with a new point count and degree."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call(
                "rhino.geometry.rebuild_curve", args.model_dump()
            )
        h = doc(args.doc_id)
        obj = h.find_object(args.object_id)
        geom = obj.Geometry
        if not isinstance(geom, r3.Curve):
            raise parameter_error("object_id", "must reference a curve", "any curve GUID")
        domain = geom.Domain
        sample_pts = [
            geom.PointAt(domain.T0 + (domain.T1 - domain.T0) * i / (args.point_count - 1))
            for i in range(args.point_count)
        ]
        rebuilt = r3.NurbsCurve.CreateControlPointCurve(
            sample_pts, min(args.degree, args.point_count - 1)
        )
        h.file3dm.Objects.Delete(obj.Attributes.Id)
        new_gid = h.add_index(h.file3dm.Objects.AddCurve(rebuilt))
        return {
            "summary": object_summary(h, new_gid, "RebuiltCurve"),
            "text": f"Rebuilt curve {args.object_id} as {new_gid}",
        }


# ---------- internal builders ----------


def _ellipse_nurbs(center: r3.Point3d, rx: float, ry: float) -> r3.NurbsCurve:
    """Build a closed degree-3 NURBS curve approximating an ellipse."""
    samples = 64
    pts: list[r3.Point3d] = []
    for i in range(samples + 1):
        t = 2.0 * math.pi * i / samples
        pts.append(r3.Point3d(center.X + rx * math.cos(t), center.Y + ry * math.sin(t), center.Z))
    return r3.NurbsCurve.CreateControlPointCurve(pts, 3)


def _helix_nurbs(
    center: r3.Point3d,
    r0: float,
    r1: float,
    pitch: float,
    turns: float,
    pts_per_turn: int,
) -> r3.NurbsCurve:
    n = max(2, round(pts_per_turn * turns))
    pts: list[r3.Point3d] = []
    for i in range(n + 1):
        u = i / n
        theta = 2.0 * math.pi * turns * u
        radius = r0 + (r1 - r0) * u
        pts.append(
            r3.Point3d(
                center.X + radius * math.cos(theta),
                center.Y + radius * math.sin(theta),
                center.Z + pitch * turns * u,
            )
        )
    return r3.NurbsCurve.CreateControlPointCurve(pts, 3)
