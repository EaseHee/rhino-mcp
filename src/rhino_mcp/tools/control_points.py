"""Control point get/set tools.

Bridge-only — requires live Rhino for NURBS control point access.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _GetCPIn(BaseModel):
    object_id: str = Field(..., description="GUID of the NURBS curve or surface.")


class _SetCPIn(BaseModel):
    object_id: str = Field(..., description="GUID of the NURBS curve or surface.")
    points: list[Point3dModel] = Field(
        ..., min_length=1,
        description="New control point positions (same count and order as existing).",
    )
    weights: list[float] | None = Field(
        None, description="Optional weights for rational curves/surfaces.",
    )


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Get Control Points", "readOnlyHint": True})
    def rhino_get_control_points(args: _GetCPIn) -> dict[str, Any]:
        """Get all control points (and weights) of a NURBS curve or surface."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_get_control_points")
        return runtime().require_bridge().call("rhino.cp.get", args.model_dump())

    @mcp.tool(annotations={"title": "Set Control Points"})
    def rhino_set_control_points(args: _SetCPIn) -> dict[str, Any]:
        """Replace control points of a NURBS curve or surface."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_set_control_points")
        return runtime().require_bridge().call("rhino.cp.set", args.model_dump())
