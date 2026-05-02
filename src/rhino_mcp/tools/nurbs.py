"""NURBS editing tools: rebuild, evaluate, unroll, surface from points.

Bridge-only — requires live Rhino for advanced NURBS operations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _RebuildSurfaceIn(BaseModel):
    object_id: str
    point_count_u: int = Field(..., ge=2, le=10000, description="U-direction control point count.")
    point_count_v: int = Field(..., ge=2, le=10000, description="V-direction control point count.")
    degree_u: int = Field(3, ge=1, le=11, description="U-direction degree.")
    degree_v: int = Field(3, ge=1, le=11, description="V-direction degree.")


class _SurfaceFromPointsIn(BaseModel):
    points: list[list[Point3dModel]] = Field(
        ..., min_length=2, description="2D grid of points (rows x cols).",
    )
    degree_u: int = Field(3, ge=1, le=11)
    degree_v: int = Field(3, ge=1, le=11)
    layer: str | None = None
    name: str | None = None


class _UnrollIn(BaseModel):
    object_id: str = Field(..., description="GUID of the surface or polysurface to unroll.")
    explode: bool = Field(False, description="Explode the result into separate pieces.")


class _ClosestPointIn(BaseModel):
    object_id: str = Field(..., description="GUID of the surface.")
    test_point: Point3dModel


class _EvaluateSurfaceIn(BaseModel):
    object_id: str
    u: float
    v: float


def register(mcp: Any, mode: str) -> None:
    # NOTE: rhino_rebuild_curve already exists in geometry.py (Mode.BOTH)
    # with standalone implementation. No duplicate here.

    @mcp.tool(annotations={"title": "Rebuild Surface"})
    def rhino_rebuild_surface(args: _RebuildSurfaceIn) -> dict[str, Any]:
        """Rebuild a surface with new point counts and degrees in U/V."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_rebuild_surface")
        return runtime().require_bridge().call("rhino.nurbs.rebuild_surface", args.model_dump())

    @mcp.tool(annotations={"title": "Surface From Points"})
    def rhino_surface_from_points(args: _SurfaceFromPointsIn) -> dict[str, Any]:
        """Create a NURBS surface from a 2D grid of control points."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_surface_from_points")
        return runtime().require_bridge().call("rhino.nurbs.surface_from_points", args.model_dump())

    @mcp.tool(annotations={"title": "Unroll Surface"})
    def rhino_unroll(args: _UnrollIn) -> dict[str, Any]:
        """Unroll a developable surface or polysurface flat."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_unroll")
        return runtime().require_bridge().call("rhino.nurbs.unroll", args.model_dump())

    @mcp.tool(annotations={"title": "Surface Closest Point", "readOnlyHint": True})
    def rhino_surface_closest_point(args: _ClosestPointIn) -> dict[str, Any]:
        """Find the UV parameters and 3D point closest to a test point on a surface."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_surface_closest_point")
        return runtime().require_bridge().call("rhino.nurbs.closest_point", args.model_dump())

    @mcp.tool(annotations={"title": "Evaluate Surface", "readOnlyHint": True})
    def rhino_evaluate_surface(args: _EvaluateSurfaceIn) -> dict[str, Any]:
        """Evaluate a surface at UV parameters to get 3D point, normal, and tangents."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_evaluate_surface")
        return runtime().require_bridge().call("rhino.nurbs.evaluate", args.model_dump())
