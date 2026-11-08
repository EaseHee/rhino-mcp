"""SubD tools: create from mesh, convert to NURBS, inspect topology.

Creation and NURBS conversion are bridge-only (rhino3dm has no SubD
constructors). ``rhino_subd_inspect`` also works in standalone: rhino3dm
8.32+ exposes read-only SubD vertex/edge/face iterators with tags and
sharpness, which is enough to report topology, creases, and corners of a
SubD read from a .3dm file.
"""

from __future__ import annotations

from typing import Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import bridge_call, doc, subd_summary
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error, unsupported_in_standalone
from rhino_mcp.utils.registry import Mode
from rhino_mcp.utils.serialization import bbox_to_dict


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


class _SubDInspectIn(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )
    object_id: str = Field(..., description="GUID of the SubD object.")
    include_creases: bool = Field(
        True,
        description="List crease/sharp edges (index, tag, end sharpness).",
    )
    limit: int = Field(
        200,
        ge=1,
        le=2000,
        description="Maximum number of crease edges / corner vertices listed.",
    )


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

    @mcp.tool(annotations={"title": "Inspect SubD", "readOnlyHint": True})
    def rhino_subd_inspect(args: _SubDInspectIn) -> dict[str, Any]:
        """Report SubD topology: vertex/edge/face counts, vertex and edge tags,
        boundary / crease / sharp edges, corners, and face side-count histogram.

        Standalone reads the SubD control net through rhino3dm 8.32+ iterators.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.subd.inspect", args.model_dump())
        h = doc(args.doc_id)
        geom: Any = h.find_object(args.object_id).Geometry
        if not isinstance(geom, r3.SubD):
            raise parameter_error("object_id", f"must reference a SubD (got {type(geom).__name__})")
        summary = subd_summary(geom, include_creases=args.include_creases, limit=args.limit)
        summary["object_id"] = args.object_id
        summary["bounding_box"] = bbox_to_dict(geom.GetBoundingBox())  # type: ignore[call-arg]
        return {
            "summary": summary,
            "text": (
                f"SubD {args.object_id}: {summary['vertex_count']} vertices, "
                f"{summary['edge_count']} edges, {summary['face_count']} faces, "
                f"{summary['crease_edge_count']} crease edge(s)"
            ),
        }
