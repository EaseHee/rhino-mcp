"""Curve extraction tools: duplicate edges/borders, isocurves, Make2D.

Bridge-only — requires live Rhino for extraction operations.
Note: contour and section already exist in analysis.py.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import MAX_OBJECT_IDS
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _DupEdgeIn(BaseModel):
    object_id: str = Field(..., description="GUID of the Brep.")
    edge_indices: list[int] | None = Field(
        None, description="Specific edge indices to extract (None = all edges).",
    )
    layer: str | None = None


class _DupBorderIn(BaseModel):
    object_id: str = Field(..., description="GUID of the surface or mesh.")
    border_type: str = Field(
        "all",
        description="'all', 'naked' (outer), or 'interior'.",
    )
    layer: str | None = None


class _IsocurveIn(BaseModel):
    object_id: str = Field(..., description="GUID of the surface.")
    direction: int = Field(0, ge=0, le=1, description="0 = U-direction, 1 = V-direction.")
    parameter: float = Field(..., description="Surface parameter value for the isocurve.")
    layer: str | None = None


class _Make2DIn(BaseModel):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    view_name: str | None = Field(None, description="Named view to project from (None = active viewport).")
    show_hidden: bool = Field(False, description="Include hidden lines.")
    layer: str | None = None


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Duplicate Edges"})
    def rhino_dup_edge(args: _DupEdgeIn) -> dict[str, Any]:
        """Extract edge curves from a Brep (all or specific indices)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dup_edge")
        return runtime().require_bridge().call("rhino.extract.dup_edge", args.model_dump())

    @mcp.tool(annotations={"title": "Duplicate Border"})
    def rhino_dup_border(args: _DupBorderIn) -> dict[str, Any]:
        """Extract border curves from a surface or mesh."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dup_border")
        return runtime().require_bridge().call("rhino.extract.dup_border", args.model_dump())

    @mcp.tool(annotations={"title": "Extract Isocurve"})
    def rhino_isocurve(args: _IsocurveIn) -> dict[str, Any]:
        """Extract an isocurve from a surface at a specific U or V parameter."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_isocurve")
        return runtime().require_bridge().call("rhino.extract.isocurve", args.model_dump())

    @mcp.tool(annotations={"title": "Make 2D Drawing"})
    def rhino_make2d(args: _Make2DIn) -> dict[str, Any]:
        """Generate a 2D drawing projection of 3D objects."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_make2d")
        return runtime().require_bridge().call("rhino.extract.make2d", args.model_dump())
