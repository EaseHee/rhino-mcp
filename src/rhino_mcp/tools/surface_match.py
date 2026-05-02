"""Surface matching tools: match, blend, merge.

Bridge-only — requires live Rhino for advanced surface operations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _MatchSurfaceIn(BaseModel):
    surface_id: str = Field(..., description="GUID of the surface to modify.")
    target_id: str = Field(..., description="GUID of the target surface to match to.")
    continuity: int = Field(2, ge=0, le=3, description="0=position, 1=tangent, 2=curvature, 3=G3.")


class _BlendSurfaceIn(BaseModel):
    edge_id_1: str = Field(..., description="GUID of the first edge or surface.")
    edge_id_2: str = Field(..., description="GUID of the second edge or surface.")
    continuity: int = Field(2, ge=0, le=3)
    layer: str | None = None
    name: str | None = None


class _MergeSurfacesIn(BaseModel):
    surface_ids: list[str] = Field(..., min_length=2, description="GUIDs of surfaces to merge.")
    tolerance: float = Field(0.001, gt=0, description="Merge tolerance.")


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Match Surface"})
    def rhino_match_surface(args: _MatchSurfaceIn) -> dict[str, Any]:
        """Adjust a surface edge to match the continuity of a target surface."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_match_surface")
        return runtime().require_bridge().call("rhino.surface_match.match", args.model_dump())

    @mcp.tool(annotations={"title": "Blend Surface Edges"})
    def rhino_blend_surface_edges(args: _BlendSurfaceIn) -> dict[str, Any]:
        """Create a blend surface connecting two surface edges with continuity control."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_blend_surface_edges")
        return runtime().require_bridge().call("rhino.surface_match.blend", args.model_dump())

    @mcp.tool(annotations={"title": "Merge Surfaces"})
    def rhino_merge_surfaces(args: _MergeSurfacesIn) -> dict[str, Any]:
        """Merge multiple surfaces into a single surface."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_merge_surfaces")
        return runtime().require_bridge().call("rhino.surface_match.merge", args.model_dump())
