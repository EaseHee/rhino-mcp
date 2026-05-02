"""Deformation tools: bend, twist, taper, flow along curve.

Bridge-only — requires live Rhino for RhinoCommon deformation operations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _BendIn(BaseModel):
    object_ids: list[str] = Field(..., min_length=1)
    start: Point3dModel = Field(..., description="Bend axis start point.")
    end: Point3dModel = Field(..., description="Bend axis end point.")
    point: Point3dModel = Field(..., description="Through point defining the bend.")
    make_copy: bool = False


class _TwistIn(BaseModel):
    object_ids: list[str] = Field(..., min_length=1)
    axis_start: Point3dModel = Field(..., description="Twist axis start.")
    axis_end: Point3dModel = Field(..., description="Twist axis end.")
    angle_degrees: float = Field(..., description="Twist angle in degrees.")
    make_copy: bool = False


class _TaperIn(BaseModel):
    object_ids: list[str] = Field(..., min_length=1)
    axis_start: Point3dModel = Field(..., description="Taper axis start.")
    axis_end: Point3dModel = Field(..., description="Taper axis end.")
    start_radius: float = Field(..., gt=0)
    end_radius: float = Field(..., gt=0)
    make_copy: bool = False


class _FlowIn(BaseModel):
    object_ids: list[str] = Field(..., min_length=1)
    base_curve_id: str = Field(..., description="GUID of the base curve.")
    target_curve_id: str = Field(..., description="GUID of the target curve.")
    make_copy: bool = True


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Bend"})
    def rhino_bend(args: _BendIn) -> dict[str, Any]:
        """Bend objects along an axis through a specified point."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_bend")
        return runtime().require_bridge().call("rhino.deform.bend", args.model_dump())

    @mcp.tool(annotations={"title": "Twist"})
    def rhino_twist(args: _TwistIn) -> dict[str, Any]:
        """Twist objects around an axis by a specified angle."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_twist")
        return runtime().require_bridge().call("rhino.deform.twist", args.model_dump())

    @mcp.tool(annotations={"title": "Taper"})
    def rhino_taper(args: _TaperIn) -> dict[str, Any]:
        """Taper objects along an axis with start/end radii."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_taper")
        return runtime().require_bridge().call("rhino.deform.taper", args.model_dump())

    @mcp.tool(annotations={"title": "Flow Along Curve"})
    def rhino_flow_along_curve(args: _FlowIn) -> dict[str, Any]:
        """Reposition objects from a base curve onto a target curve."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_flow_along_curve")
        return runtime().require_bridge().call("rhino.deform.flow_along_curve", args.model_dump())
