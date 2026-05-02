"""Material creation/assignment, plus render-viewport (bridge-only)."""

from __future__ import annotations

from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import ColorRGBA
from rhino_mcp.tools._helpers import doc, find_material_index
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _MaterialCreateIn(_DocArg):
    name: str = Field(..., min_length=1)
    diffuse: ColorRGBA = Field(default_factory=ColorRGBA)
    transparency: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    glossiness: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class _MaterialAssignIn(_DocArg):
    material_name: str
    object_ids: list[str] = Field(..., min_length=1)


class _RenderIn(_DocArg):
    width: Annotated[int, Field(ge=64, le=8192)] = 1280
    height: Annotated[int, Field(ge=64, le=8192)] = 720
    output_path: str


def _find_material(handle, name: str) -> int:
    idx = find_material_index(handle, name)
    if idx is None:
        raise not_found_error("material", name)
    return idx


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Create Material", "readOnlyHint": False})
    def rhino_material_create(args: _MaterialCreateIn) -> dict[str, Any]:
        """Create a material with diffuse colour, transparency, and glossiness."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.material.create", args.model_dump())
        h = doc(args.doc_id)
        m = r3.Material()
        m.Name = args.name
        m.DiffuseColor = (args.diffuse.r, args.diffuse.g, args.diffuse.b, args.diffuse.a)
        m.Transparency = args.transparency
        m.Shine = args.glossiness * 255  # rhino3dm uses 0..255
        idx = h.file3dm.Materials.Add(m)
        return {
            "summary": {"name": args.name, "index": idx, "doc_id": h.doc_id},
            "text": f"Created material '{args.name}' (index {idx})",
        }

    @mcp.tool(annotations={"title": "Assign Material", "readOnlyHint": False})
    def rhino_material_assign(args: _MaterialAssignIn) -> dict[str, Any]:
        """Assign an existing material to one or more objects."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.material.assign", args.model_dump())
        h = doc(args.doc_id)
        idx = _find_material(h, args.material_name)
        updated: list[str] = []
        for gid in args.object_ids:
            obj = h.find_object(gid)
            attrs = obj.Attributes
            attrs.MaterialIndex = idx
            attrs.MaterialSource = r3.ObjectMaterialSource.MaterialFromObject
            geom = obj.Geometry
            h.file3dm.Objects.Delete(obj.Attributes.Id)
            new_id = h.file3dm.Objects.Add(geom, attrs)
            updated.append(h.add_index(new_id))
        return {
            "summary": {"material": args.material_name, "object_ids": updated},
            "text": f"Assigned '{args.material_name}' to {len(updated)} object(s)",
        }

    if mode is Mode.STANDALONE:
        return  # bridge-only render tool below

    @mcp.tool(annotations={"title": "Render Viewport", "readOnlyHint": False})
    def rhino_render_viewport(args: _RenderIn) -> dict[str, Any]:
        """Render the active viewport to an image file (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_render_viewport")
        return runtime().require_bridge().call("rhino.render.viewport", args.model_dump())
