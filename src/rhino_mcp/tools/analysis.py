"""Geometry analysis tools (area/volume/bbox/distance + advanced bridge-only)."""

from __future__ import annotations

from typing import Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import MAX_OBJECT_IDS, doc, to_point
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error, unsupported_in_standalone
from rhino_mcp.utils.registry import Mode
from rhino_mcp.utils.serialization import bbox_to_dict


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _ObjectIn(_DocArg):
    object_id: str


class _ObjectsIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)


class _DistancePointsIn(_DocArg):
    point_a: Point3dModel
    point_b: Point3dModel


class _SectionIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    plane_origin: Point3dModel
    plane_normal: Point3dModel


class _ContourIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    base_point: Point3dModel
    direction: Point3dModel
    interval: float = Field(..., gt=0)


def _measure_area(geom) -> float | None:
    if isinstance(geom, r3.Brep):
        # rhino3dm Brep.GetArea is not exposed; approximate via face NurbsSurface sample.
        return None
    if isinstance(geom, r3.Mesh):
        # Sum triangle/quad areas from vertices.
        total = 0.0
        for i in range(geom.Faces.__len__()):
            face = geom.Faces[i]
            a = geom.Vertices[face[0]]
            b = geom.Vertices[face[1]]
            c = geom.Vertices[face[2]]
            d = geom.Vertices[face[3]]
            total += _triangle_area(a, b, c)
            if face[2] != face[3]:
                total += _triangle_area(a, c, d)
        return total
    return None


def _triangle_area(a, b, c) -> float:
    ux, uy, uz = b.X - a.X, b.Y - a.Y, b.Z - a.Z
    vx, vy, vz = c.X - a.X, c.Y - a.Y, c.Z - a.Z
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    return 0.5 * (cx * cx + cy * cy + cz * cz) ** 0.5


def _measure_volume(geom) -> float | None:
    if isinstance(geom, r3.Mesh):
        # Volume via signed tetrahedra from origin.
        total = 0.0
        for i in range(geom.Faces.__len__()):
            face = geom.Faces[i]
            a = geom.Vertices[face[0]]
            b = geom.Vertices[face[1]]
            c = geom.Vertices[face[2]]
            d = geom.Vertices[face[3]]
            total += _tet_volume(a, b, c)
            if face[2] != face[3]:
                total += _tet_volume(a, c, d)
        return abs(total)
    return None


def _tet_volume(a, b, c) -> float:
    return (a.X * (b.Y * c.Z - b.Z * c.Y) - a.Y * (b.X * c.Z - b.Z * c.X) + a.Z * (b.X * c.Y - b.Y * c.X)) / 6.0


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Object Area", "readOnlyHint": True, "idempotentHint": True})
    def rhino_area(args: _ObjectIn) -> dict[str, Any]:
        """Compute the surface area of a mesh (Brep area requires bridge)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.analysis.area", args.model_dump())
        h = doc(args.doc_id)
        obj = h.find_object(args.object_id)
        area = _measure_area(obj.Geometry)
        if area is None:
            raise unsupported_in_standalone("rhino_area for this geometry type")
        return {"summary": {"object_id": args.object_id, "area": area}, "text": f"Area = {area:.6f}"}

    @mcp.tool(annotations={"title": "Object Volume", "readOnlyHint": True, "idempotentHint": True})
    def rhino_volume(args: _ObjectIn) -> dict[str, Any]:
        """Compute the volume of a closed mesh (Brep volume requires bridge)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.analysis.volume", args.model_dump())
        h = doc(args.doc_id)
        obj = h.find_object(args.object_id)
        volume = _measure_volume(obj.Geometry)
        if volume is None:
            raise unsupported_in_standalone("rhino_volume for this geometry type")
        return {"summary": {"object_id": args.object_id, "volume": volume}, "text": f"Volume = {volume:.6f}"}

    @mcp.tool(annotations={"title": "Object Bounding Box", "readOnlyHint": True, "idempotentHint": True})
    def rhino_bounding_box(args: _ObjectsIn) -> dict[str, Any]:
        """Return the union bounding box of one or more objects."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.analysis.bounding_box", args.model_dump())
        h = doc(args.doc_id)
        bboxes = [h.find_object(g).Geometry.GetBoundingBox() for g in args.object_ids]
        union = bboxes[0]
        for b in bboxes[1:]:
            union = r3.BoundingBox(
                r3.Point3d(min(union.Min.X, b.Min.X), min(union.Min.Y, b.Min.Y), min(union.Min.Z, b.Min.Z)),
                r3.Point3d(max(union.Max.X, b.Max.X), max(union.Max.Y, b.Max.Y), max(union.Max.Z, b.Max.Z)),
            )
        return {
            "summary": {"object_ids": args.object_ids, "bounding_box": bbox_to_dict(union)},
            "text": f"Computed bounding box of {len(args.object_ids)} object(s)",
        }

    @mcp.tool(annotations={"title": "Distance Between Two Points", "readOnlyHint": True, "idempotentHint": True})
    def rhino_distance(args: _DistancePointsIn) -> dict[str, Any]:
        """Euclidean distance between two points."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.analysis.distance", args.model_dump())
        a = to_point(args.point_a)
        b = to_point(args.point_b)
        d = ((a.X - b.X) ** 2 + (a.Y - b.Y) ** 2 + (a.Z - b.Z) ** 2) ** 0.5
        if d == 0:
            raise parameter_error("point_a/point_b", "points are coincident")
        return {"summary": {"distance": d}, "text": f"Distance = {d:.6f}"}

    if mode is Mode.STANDALONE:
        return  # bridge-only analysis tools below

    @mcp.tool(annotations={"title": "Curvature Analysis", "readOnlyHint": True})
    def rhino_curvature_analysis(args: _ObjectIn) -> dict[str, Any]:
        """Sample Gaussian/mean curvature of a surface (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_curvature_analysis")
        return runtime().require_bridge().call("rhino.analysis.curvature", args.model_dump())

    @mcp.tool(annotations={"title": "Draft-Angle Analysis", "readOnlyHint": True})
    def rhino_draft_angle(args: _ObjectIn) -> dict[str, Any]:
        """Compute draft angles relative to the world Z axis (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_draft_angle")
        return runtime().require_bridge().call("rhino.analysis.draft_angle", args.model_dump())

    @mcp.tool(annotations={"title": "Zebra Analysis", "readOnlyHint": True})
    def rhino_zebra(args: _ObjectIn) -> dict[str, Any]:
        """Run zebra-stripe surface continuity analysis (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_zebra")
        return runtime().require_bridge().call("rhino.analysis.zebra", args.model_dump())

    @mcp.tool(annotations={"title": "Section Through Plane", "readOnlyHint": False})
    def rhino_section(args: _SectionIn) -> dict[str, Any]:
        """Slice the listed objects with a plane (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_section")
        return runtime().require_bridge().call("rhino.analysis.section", args.model_dump())

    @mcp.tool(annotations={"title": "Contour Curves", "readOnlyHint": False})
    def rhino_contour(args: _ContourIn) -> dict[str, Any]:
        """Generate equally spaced section curves (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_contour")
        return runtime().require_bridge().call("rhino.analysis.contour", args.model_dump())
