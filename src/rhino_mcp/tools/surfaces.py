"""Surface-creation tools.

``rhino_plane_surface`` and ``rhino_extrude`` have standalone fallbacks using
``rhino3dm.NurbsSurface`` and ``rhino3dm.Extrusion``. The remaining surface
tools (loft, sweep, network, patch, blend, fillet, offset, revolve) require
RhinoCommon and are bridge-only.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import PlaneModel, Vector3dModel
from rhino_mcp.tools._helpers import (
    add_object_with_attrs,
    doc,
    object_summary,
    text_for,
    to_point,
    to_vector,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )
    layer: str | None = Field(None)
    name: str | None = Field(None)


class _PlaneSurfaceIn(_DocArg):
    plane: PlaneModel
    width: Annotated[float, Field(gt=0)]
    height: Annotated[float, Field(gt=0)]


class _ExtrudeIn(_DocArg):
    profile_id: str = Field(..., description="GUID of a curve to extrude.")
    direction: Vector3dModel
    distance: Annotated[float, Field(gt=0)]
    capped: bool = Field(True)


class _RevolveIn(_DocArg):
    profile_id: str
    axis_start: list[float] = Field(..., min_length=3, max_length=3)
    axis_end: list[float] = Field(..., min_length=3, max_length=3)
    angle_degrees: Annotated[float, Field(gt=0, le=360)] = 360


class _LoftIn(_DocArg):
    profile_ids: list[str] = Field(..., min_length=2)
    closed: bool = Field(False)
    loft_type: str = Field("normal", description="normal | loose | tight | straight | uniform")


class _SweepIn(_DocArg):
    rail_id: str
    profile_ids: list[str] = Field(..., min_length=1)


class _Sweep2In(_DocArg):
    rail1_id: str
    rail2_id: str
    profile_ids: list[str] = Field(..., min_length=1)


class _NetworkIn(_DocArg):
    u_curve_ids: list[str] = Field(..., min_length=2)
    v_curve_ids: list[str] = Field(..., min_length=2)


class _PatchIn(_DocArg):
    boundary_curve_ids: list[str] = Field(..., min_length=1)
    span_count: Annotated[int, Field(ge=2, le=64)] = 10


class _BlendIn(_DocArg):
    edge_a_id: str
    edge_b_id: str
    bulge: Annotated[float, Field(ge=0)] = 1.0


class _FilletIn(_DocArg):
    surface_a_id: str
    surface_b_id: str
    radius: Annotated[float, Field(gt=0)]


class _OffsetIn(_DocArg):
    surface_id: str
    distance: float
    tolerance: Annotated[float, Field(gt=0)] = 0.001


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Add Plane Surface", "readOnlyHint": False})
    def rhino_plane_surface(args: _PlaneSurfaceIn) -> dict[str, Any]:
        """Add a finite plane (rectangular trim) on the given plane."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.surface.plane_surface", args.model_dump())
        # Standalone: build a ruled surface between the two long edges of the rectangle.
        h = doc(args.doc_id)
        origin = to_point(args.plane.origin)
        w, ht = args.width, args.height
        edge0 = r3.LineCurve(
            r3.Point3d(origin.X - w / 2, origin.Y - ht / 2, origin.Z),
            r3.Point3d(origin.X + w / 2, origin.Y - ht / 2, origin.Z),
        )
        edge1 = r3.LineCurve(
            r3.Point3d(origin.X - w / 2, origin.Y + ht / 2, origin.Z),
            r3.Point3d(origin.X + w / 2, origin.Y + ht / 2, origin.Z),
        )
        srf = r3.NurbsSurface.CreateRuledSurface(edge0, edge1)
        gid = add_object_with_attrs(h, "Add", srf, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "PlaneSurface"), "text": text_for("PlaneSurface", gid)}

    @mcp.tool(annotations={"title": "Extrude Curve", "readOnlyHint": False})
    def rhino_extrude(args: _ExtrudeIn) -> dict[str, Any]:
        """Linearly extrude a profile curve by ``distance`` along ``direction``."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.surface.extrude", args.model_dump())
        # Standalone: rhino3dm Extrusion
        h = doc(args.doc_id)
        obj = h.file3dm.Objects.FindId(args.profile_id)
        if obj is None:
            from rhino_mcp.utils.error_handling import not_found_error
            raise not_found_error("curve", args.profile_id)
        curve = obj.Geometry
        direction = to_vector(args.direction)
        length = math.sqrt(direction.X ** 2 + direction.Y ** 2 + direction.Z ** 2)
        if length == 0:
            from rhino_mcp.utils.error_handling import parameter_error
            raise parameter_error("direction", "must be non-zero")
        extrusion = r3.Extrusion.Create(curve, args.distance * length, args.capped)
        if extrusion is None:
            from rhino_mcp.utils.error_handling import parameter_error
            raise parameter_error("profile_id", "curve cannot be extruded with rhino3dm")
        gid = add_object_with_attrs(h, "Add", extrusion, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Extrusion"), "text": text_for("Extrusion", gid)}

    @mcp.tool(annotations={"title": "Revolve Curve", "readOnlyHint": False})
    def rhino_revolve(args: _RevolveIn) -> dict[str, Any]:
        """Revolve a profile curve about an axis."""
        return runtime().require_bridge().call("rhino.surface.revolve", args.model_dump())

    @mcp.tool(annotations={"title": "Loft Surfaces", "readOnlyHint": False})
    def rhino_loft(args: _LoftIn) -> dict[str, Any]:
        """Loft a sequence of profile curves into a surface."""
        return runtime().require_bridge().call("rhino.surface.loft", args.model_dump())

    @mcp.tool(annotations={"title": "Sweep1 (single rail)", "readOnlyHint": False})
    def rhino_sweep1(args: _SweepIn) -> dict[str, Any]:
        """Sweep profiles along a single rail."""
        return runtime().require_bridge().call("rhino.surface.sweep1", args.model_dump())

    @mcp.tool(annotations={"title": "Sweep2 (two rails)", "readOnlyHint": False})
    def rhino_sweep2(args: _Sweep2In) -> dict[str, Any]:
        """Sweep profiles along two rails."""
        return runtime().require_bridge().call("rhino.surface.sweep2", args.model_dump())

    @mcp.tool(annotations={"title": "Network Surface", "readOnlyHint": False})
    def rhino_network_surface(args: _NetworkIn) -> dict[str, Any]:
        """Build a surface from a network of crossing curves."""
        return runtime().require_bridge().call("rhino.surface.network", args.model_dump())

    @mcp.tool(annotations={"title": "Patch Surface", "readOnlyHint": False})
    def rhino_patch(args: _PatchIn) -> dict[str, Any]:
        """Patch a region defined by boundary curves."""
        return runtime().require_bridge().call("rhino.surface.patch", args.model_dump())

    @mcp.tool(annotations={"title": "Blend Surface Between Edges", "readOnlyHint": False})
    def rhino_blend_surface(args: _BlendIn) -> dict[str, Any]:
        """Create a blend surface between two edges."""
        return runtime().require_bridge().call("rhino.surface.blend", args.model_dump())

    @mcp.tool(annotations={"title": "Fillet Between Surfaces", "readOnlyHint": False})
    def rhino_fillet_surface(args: _FilletIn) -> dict[str, Any]:
        """Create a constant-radius fillet between two surfaces."""
        return runtime().require_bridge().call("rhino.surface.fillet", args.model_dump())

    @mcp.tool(annotations={"title": "Offset Surface", "readOnlyHint": False})
    def rhino_offset_surface(args: _OffsetIn) -> dict[str, Any]:
        """Offset a surface by ``distance`` along its normal."""
        return runtime().require_bridge().call("rhino.surface.offset", args.model_dump())
