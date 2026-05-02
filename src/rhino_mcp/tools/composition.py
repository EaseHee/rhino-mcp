"""Scene-composition tools for one-shot multi-object placement.

These tools collapse the typical "loop + transform" pattern an LLM otherwise
has to drive call-by-call. ``rhino_place_grid`` lays out a source object on a
2-D grid; ``rhino_stack_floors`` stacks copies along the world Z axis (a very
common architectural building-up move); ``rhino_scatter`` drops copies inside
a 2-D bounding box with a deterministic seed; ``rhino_replicate_along_curve``
distributes copies along a curve, optionally aligned to the local tangent.

All four work in standalone (``rhino3dm``) and bridge (RhinoCommon) modes.
"""

from __future__ import annotations

import math
import random
from typing import Annotated, Any
from uuid import UUID

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import bridge_call, doc, to_point
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _PlaceGridIn(_DocArg):
    source_object_id: str = Field(
        ...,
        description="Object to replicate. The source itself is left in place; copies fill the grid.",
    )
    base_point: Point3dModel = Field(
        ..., description="World-space anchor for cell (0, 0)."
    )
    count_x: Annotated[int, Field(ge=1, le=512, description="Cells along the X axis (>= 1).")]
    count_y: Annotated[int, Field(ge=1, le=512, description="Cells along the Y axis (>= 1).")]
    spacing_x: Annotated[float, Field(gt=0, description="Cell pitch along X (document units).")]
    spacing_y: Annotated[float, Field(gt=0, description="Cell pitch along Y (document units).")]
    skip_origin: bool = Field(
        True,
        description="When True the source remains at the (0,0) cell and is not duplicated there.",
    )
    name_prefix: str | None = Field(
        None,
        description="If set, copies are named '<prefix>_x_y' (else inherits source name).",
    )


class _StackFloorsIn(_DocArg):
    source_object_id: str = Field(..., description="Object to replicate vertically (e.g. a slab).")
    floor_count: Annotated[int, Field(ge=1, le=256, description="Number of *additional* floors above the source.")]
    floor_height: Annotated[float, Field(gt=0, description="Z spacing per floor (document units).")]
    name_prefix: str | None = Field(
        None,
        description="If set, copies are named '<prefix>_F<n>' (n starts at 1).",
    )


class _ScatterIn(_DocArg):
    source_object_id: str = Field(..., description="Object to replicate at scattered positions.")
    boundary_min: Point3dModel = Field(..., description="2-D AABB lower corner (Z is preserved from the source).")
    boundary_max: Point3dModel = Field(..., description="2-D AABB upper corner.")
    count: Annotated[int, Field(ge=1, le=2048, description="Number of copies to scatter.")]
    seed: int | None = Field(
        None,
        description="Optional RNG seed for deterministic output (recommended for tests / reproducible studies).",
    )
    rotation_jitter_deg: Annotated[float, Field(ge=0, le=360)] = Field(
        0.0,
        description="If > 0, each copy is rotated about world Z by U(-jitter, +jitter) degrees.",
    )


class _ReplicateAlongCurveIn(_DocArg):
    source_object_id: str = Field(..., description="Object to replicate along the curve.")
    curve_id: str = Field(..., description="Path curve. Copies are placed at evenly spaced parameters.")
    count: Annotated[int, Field(ge=1, le=512, description="Number of copies along the curve.")]
    align_to_tangent: bool = Field(
        True,
        description="If True, each copy is reoriented from world XY to a frame whose X axis follows the curve tangent.",
    )
    include_endpoints: bool = Field(
        True,
        description="If True, copies are placed at curve start and end inclusive (count >= 2).",
    )


def _find_obj(handle: Any, gid: str) -> Any:
    obj = handle.file3dm.Objects.FindId(gid)
    if obj is None:
        raise not_found_error("object", gid)
    return obj


def _duplicate_with_xform(handle: Any, source_obj: Any, xform: r3.Transform, *, name: str | None) -> str:
    geom = source_obj.Geometry.Duplicate()
    geom.Transform(xform)
    attrs = source_obj.Attributes
    if name is not None:
        attrs = source_obj.Attributes
        attrs.Name = name
    new_id: UUID = handle.file3dm.Objects.Add(geom, attrs)
    return handle.add_index(new_id)


def _frame_to_frame(src_origin: r3.Point3d, dst_origin: r3.Point3d, dst_x_axis: r3.Vector3d) -> r3.Transform:
    """Build a PlaneToPlane transform: world XY at ``src_origin`` → frame at ``dst_origin`` with X = ``dst_x_axis``."""
    src_plane = r3.Plane(src_origin, r3.Vector3d(1, 0, 0), r3.Vector3d(0, 1, 0))
    z = r3.Vector3d(0, 0, 1)
    x = r3.Vector3d(dst_x_axis.X, dst_x_axis.Y, dst_x_axis.Z)
    # Normalise X
    n = math.sqrt(x.X * x.X + x.Y * x.Y + x.Z * x.Z)
    if n == 0:
        x = r3.Vector3d(1, 0, 0)
    else:
        x = r3.Vector3d(x.X / n, x.Y / n, x.Z / n)
    # Y = Z x X, fall back to world-Y if the curve tangent is parallel to world Z.
    yx = z.Y * x.Z - z.Z * x.Y
    yy = z.Z * x.X - z.X * x.Z
    yz = z.X * x.Y - z.Y * x.X
    yn = math.sqrt(yx * yx + yy * yy + yz * yz)
    if yn < 1e-9:
        y = r3.Vector3d(0, 1, 0)
    else:
        y = r3.Vector3d(yx / yn, yy / yn, yz / yn)
    dst_plane = r3.Plane(dst_origin, x, y)
    return r3.Transform.PlaneToPlane(src_plane, dst_plane)


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Place Grid", "readOnlyHint": False})
    def rhino_place_grid(args: _PlaceGridIn) -> dict[str, Any]:
        """Replicate a source object on a count_x x count_y grid with given spacing.

        Returns the new object IDs in row-major (x outer, y inner) order. The
        source is preserved; when ``skip_origin`` is True the (0,0) cell is
        left untouched and the source itself fills it.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.composition.place_grid", args.model_dump())
        h = doc(args.doc_id)
        src = _find_obj(h, args.source_object_id)
        new_ids: list[str] = []
        base = to_point(args.base_point)
        for ix in range(args.count_x):
            for iy in range(args.count_y):
                if ix == 0 and iy == 0 and args.skip_origin:
                    continue
                offset = r3.Vector3d(
                    base.X + ix * args.spacing_x,
                    base.Y + iy * args.spacing_y,
                    base.Z,
                )
                xf = r3.Transform.Translation(offset)
                name = (
                    f"{args.name_prefix}_{ix}_{iy}"
                    if args.name_prefix is not None
                    else None
                )
                new_ids.append(_duplicate_with_xform(h, src, xf, name=name))
        return {
            "summary": {
                "source_object_id": args.source_object_id,
                "object_ids": new_ids,
                "count_x": args.count_x,
                "count_y": args.count_y,
            },
            "text": f"Grid placed {len(new_ids)} copies ({args.count_x}x{args.count_y})",
        }

    @mcp.tool(annotations={"title": "Stack Floors", "readOnlyHint": False})
    def rhino_stack_floors(args: _StackFloorsIn) -> dict[str, Any]:
        """Replicate a source object N times along world +Z with constant spacing.

        Architectural shortcut for "stack this slab N floors high". The source
        sits at level 0; copies populate levels 1 .. floor_count.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.composition.stack_floors", args.model_dump())
        h = doc(args.doc_id)
        src = _find_obj(h, args.source_object_id)
        new_ids: list[str] = []
        for k in range(1, args.floor_count + 1):
            xf = r3.Transform.Translation(r3.Vector3d(0, 0, k * args.floor_height))
            name = f"{args.name_prefix}_F{k}" if args.name_prefix is not None else None
            new_ids.append(_duplicate_with_xform(h, src, xf, name=name))
        return {
            "summary": {
                "source_object_id": args.source_object_id,
                "object_ids": new_ids,
                "floor_count": args.floor_count,
            },
            "text": f"Stacked {len(new_ids)} floor copies",
        }

    @mcp.tool(annotations={"title": "Scatter Inside AABB", "readOnlyHint": False})
    def rhino_scatter(args: _ScatterIn) -> dict[str, Any]:
        """Scatter ``count`` copies of a source inside a 2-D AABB with optional Z-rotation jitter.

        The boundary is interpreted in world XY; Z is taken from
        ``boundary_min.z``. Use ``seed`` for deterministic output.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.composition.scatter", args.model_dump())
        if args.boundary_max.x <= args.boundary_min.x or args.boundary_max.y <= args.boundary_min.y:
            raise parameter_error(
                "boundary_max",
                "boundary_max must be strictly greater than boundary_min on X and Y",
            )
        h = doc(args.doc_id)
        src = _find_obj(h, args.source_object_id)
        rng = random.Random(args.seed)
        z = args.boundary_min.z
        new_ids: list[str] = []
        for _ in range(args.count):
            x = rng.uniform(args.boundary_min.x, args.boundary_max.x)
            y = rng.uniform(args.boundary_min.y, args.boundary_max.y)
            xf = r3.Transform.Translation(r3.Vector3d(x, y, z))
            if args.rotation_jitter_deg > 0:
                angle = math.radians(rng.uniform(-args.rotation_jitter_deg, args.rotation_jitter_deg))
                # Rotation about local Z at the destination point (after translation).
                rot = r3.Transform.Rotation(angle, r3.Vector3d(0, 0, 1), r3.Point3d(x, y, z))
                xf = rot * xf
            new_ids.append(_duplicate_with_xform(h, src, xf, name=None))
        return {
            "summary": {
                "source_object_id": args.source_object_id,
                "object_ids": new_ids,
                "count": args.count,
                "seed": args.seed,
            },
            "text": f"Scattered {len(new_ids)} copies",
        }

    @mcp.tool(annotations={"title": "Replicate Along Curve", "readOnlyHint": False})
    def rhino_replicate_along_curve(args: _ReplicateAlongCurveIn) -> dict[str, Any]:
        """Distribute copies of a source object along a curve at evenly-spaced parameters.

        With ``align_to_tangent`` (default), each copy is reoriented so that
        the world-X direction maps to the curve tangent at its sample point.
        ``include_endpoints`` controls whether the first/last samples land on
        the curve's start/end points.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.composition.replicate_along_curve", args.model_dump())
        h = doc(args.doc_id)
        src = _find_obj(h, args.source_object_id)
        crv_obj = _find_obj(h, args.curve_id)
        crv = crv_obj.Geometry
        if not isinstance(crv, r3.Curve):
            raise parameter_error("curve_id", "must reference a curve object")
        dom = crv.Domain
        t_min, t_max = dom.T0, dom.T1
        n = args.count
        new_ids: list[str] = []
        for k in range(n):
            if n == 1:
                t = 0.5 * (t_min + t_max)
            elif args.include_endpoints:
                t = t_min + (t_max - t_min) * (k / (n - 1))
            else:
                t = t_min + (t_max - t_min) * ((k + 1) / (n + 1))
            pt = crv.PointAt(t)
            if args.align_to_tangent:
                tangent = crv.TangentAt(t)
                xf = _frame_to_frame(r3.Point3d(0, 0, 0), pt, tangent)
            else:
                xf = r3.Transform.Translation(r3.Vector3d(pt.X, pt.Y, pt.Z))
            new_ids.append(_duplicate_with_xform(h, src, xf, name=None))
        return {
            "summary": {
                "source_object_id": args.source_object_id,
                "curve_id": args.curve_id,
                "object_ids": new_ids,
                "aligned": args.align_to_tangent,
            },
            "text": f"Replicated {len(new_ids)} copies along curve {args.curve_id}",
        }
