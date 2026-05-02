"""SubD tools: create from mesh, convert to NURBS.

Bridge-only — requires live Rhino for SubD operations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _CreateSubDIn(BaseModel):
    mesh_id: str = Field(..., description="GUID of the source mesh.")
    interpolate_corners: bool = Field(True, description="Interpolate mesh corners.")
    layer: str | None = None
    name: str | None = None


class _SubDToNurbsIn(BaseModel):
    object_id: str = Field(..., description="GUID of the SubD object.")
    packed: bool = Field(False, description="Pack faces for minimal seams.")
    layer: str | None = None
    name: str | None = None


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Create SubD from Mesh"})
    def rhino_create_subd(args: _CreateSubDIn) -> dict[str, Any]:
        """Create a SubD object from an existing mesh."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_create_subd")
        return runtime().require_bridge().call("rhino.subd.create", args.model_dump())

    @mcp.tool(annotations={"title": "SubD to NURBS"})
    def rhino_subd_to_nurbs(args: _SubDToNurbsIn) -> dict[str, Any]:
        """Convert a SubD object to a NURBS polysurface (Brep)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_subd_to_nurbs")
        return runtime().require_bridge().call("rhino.subd.to_nurbs", args.model_dump())
