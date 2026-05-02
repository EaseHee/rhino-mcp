"""Annotation tools (text dots, dimensions, leaders, hatches, clipping planes).

rhino3dm exposes the data classes (Text, TextDot, DimLinear, etc.), so we can
add them in standalone mode. Bridge mode delegates so that styling and
auto-update behaviour follow Rhino's annotation system.
"""

from __future__ import annotations

from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import PlaneModel, Point3dModel
from rhino_mcp.tools._helpers import (
    add_object_with_attrs,
    doc,
    object_summary,
    text_for,
    to_point,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )
    layer: str | None = Field(None)
    name: str | None = Field(None)


class _TextDotIn(_DocArg):
    text: str = Field(..., min_length=1)
    location: Point3dModel


class _TextIn(_DocArg):
    text: str = Field(..., min_length=1)
    location: Point3dModel
    height: Annotated[float, Field(gt=0)] = 1.0


class _LinearDimIn(_DocArg):
    point_a: Point3dModel
    point_b: Point3dModel
    plane: PlaneModel | None = None


class _AngularDimIn(_DocArg):
    center: Point3dModel
    point_a: Point3dModel
    point_b: Point3dModel


class _LeaderIn(_DocArg):
    points: list[Point3dModel] = Field(..., min_length=2)
    text: str = Field("")


class _HatchIn(_DocArg):
    boundary_curve_ids: list[str] = Field(..., min_length=1)
    pattern: str = Field("Solid")


class _ClipPlaneIn(_DocArg):
    plane: PlaneModel


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Add Text Dot", "readOnlyHint": False})
    def rhino_text_dot(args: _TextDotIn) -> dict[str, Any]:
        """Add a small label that always faces the camera in Rhino."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.annotation.text_dot", args.model_dump())
        h = doc(args.doc_id)
        td = r3.TextDot(args.text, to_point(args.location))
        gid = add_object_with_attrs(h, "AddTextDot", td, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "TextDot"), "text": text_for("TextDot", gid)}

    @mcp.tool(annotations={"title": "Add Text Annotation", "readOnlyHint": False})
    def rhino_text(args: _TextIn) -> dict[str, Any]:
        """Add 3D text annotation. Bridge mode honours the active dim style; standalone uses text-dot fallback."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.annotation.text", args.model_dump())
        # rhino3dm Text construction is read-only via OpenNURBS; emulate as text dot.
        h = doc(args.doc_id)
        td = r3.TextDot(args.text, to_point(args.location))
        gid = add_object_with_attrs(h, "AddTextDot", td, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Text"), "text": text_for("Text(dot)", gid)}

    if mode is Mode.STANDALONE:
        return  # bridge-only annotation tools below

    @mcp.tool(annotations={"title": "Linear Dimension", "readOnlyHint": False})
    def rhino_dimension_linear(args: _LinearDimIn) -> dict[str, Any]:
        """Add a linear dimension between two points."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dimension_linear")
        return runtime().require_bridge().call("rhino.annotation.dim_linear", args.model_dump())

    @mcp.tool(annotations={"title": "Aligned Dimension", "readOnlyHint": False})
    def rhino_dimension_aligned(args: _LinearDimIn) -> dict[str, Any]:
        """Add an aligned dimension between two points."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dimension_aligned")
        return runtime().require_bridge().call("rhino.annotation.dim_aligned", args.model_dump())

    @mcp.tool(annotations={"title": "Angular Dimension", "readOnlyHint": False})
    def rhino_dimension_angular(args: _AngularDimIn) -> dict[str, Any]:
        """Add an angular dimension at a vertex."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_dimension_angular")
        return runtime().require_bridge().call("rhino.annotation.dim_angular", args.model_dump())

    @mcp.tool(annotations={"title": "Add Leader", "readOnlyHint": False})
    def rhino_leader(args: _LeaderIn) -> dict[str, Any]:
        """Add a multi-point leader (with optional text)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_leader")
        return runtime().require_bridge().call("rhino.annotation.leader", args.model_dump())

    @mcp.tool(annotations={"title": "Add Hatch", "readOnlyHint": False})
    def rhino_hatch(args: _HatchIn) -> dict[str, Any]:
        """Add a hatch over the given closed curves."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_hatch")
        return runtime().require_bridge().call("rhino.annotation.hatch", args.model_dump())

    @mcp.tool(annotations={"title": "Clipping Plane", "readOnlyHint": False})
    def rhino_clipping_plane(args: _ClipPlaneIn) -> dict[str, Any]:
        """Add a clipping plane to all viewports."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_clipping_plane")
        return runtime().require_bridge().call("rhino.annotation.clipping_plane", args.model_dump())
