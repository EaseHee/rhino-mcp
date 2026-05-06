"""File I/O tools (open/save 3DM, export OBJ/STL, screenshot, import)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.document import registry
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _OpenIn(BaseModel):
    path: str = Field(..., description="Absolute path to a .3dm file.")
    doc_id: str | None = Field(None, description="Optional doc_id to bind; auto-generated if omitted.")


class _SaveIn(_DocArg):
    path: str | None = Field(None, description="Absolute path; defaults to the previously opened file.")
    version: Annotated[int, Field(ge=2, le=8)] = 8


class _ExportIn(_DocArg):
    path: str
    object_ids: list[str] | None = Field(None, description="Restrict export; default = all.")


class _ScreenshotIn(_DocArg):
    path: str = Field(..., description="Absolute output path for the PNG file.")
    width: Annotated[int, Field(ge=64, le=8192, description="Image width in pixels.")] = 1280
    height: Annotated[int, Field(ge=64, le=8192, description="Image height in pixels.")] = 720
    as_base64: bool = Field(
        False,
        description=(
            "If true, the response also carries the PNG bytes inline as "
            "``image_base64`` so the LLM can inspect the rendering without a "
            "second file read."
        ),
    )
    mime: str = Field("image/png", description="Output MIME type (PNG only).")


class _ViewportPreviewIn(_DocArg):
    path: str = Field(..., description="Absolute output PNG path.")
    width: Annotated[int, Field(ge=64, le=8192)] = 1280
    height: Annotated[int, Field(ge=64, le=8192)] = 720
    selection_ids: list[str] | None = Field(
        None,
        description="Object GUIDs to spotlight; everything else is ghosted or hidden.",
    )
    layers: list[str] | None = Field(
        None,
        description="Full-path layer names to spotlight (e.g. 'Arch::Walls').",
    )
    ghost_others: bool = Field(
        True,
        description=(
            "When True, non-target objects stay visible but unselected; when "
            "False they are hidden for the duration of the capture and restored "
            "afterwards."
        ),
    )
    zoom_to_selection: bool = Field(
        True,
        description="When True, run _Zoom _Selected before capturing.",
    )


def _resolve_objects(handle, ids: list[str] | None) -> list[r3.File3dmObject]:
    if not ids:
        return [handle.file3dm.Objects[i] for i in range(len(handle.file3dm.Objects))]
    out: list[r3.File3dmObject] = []
    for gid in ids:
        out.append(handle.find_object(gid))
    return out


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Open 3DM File", "readOnlyHint": False})
    def rhino_open(args: _OpenIn) -> dict[str, Any]:
        """Open a .3dm file and bind it to a doc_id."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.io.open", args.model_dump())
        handle = registry().open(args.path, args.doc_id)
        return {
            "summary": {
                "doc_id": handle.doc_id,
                "path": str(handle.path),
                "object_count": len(handle.file3dm.Objects),
                "layer_count": len(handle.file3dm.Layers),
            },
            "text": f"Opened {handle.path} as {handle.doc_id}",
        }

    @mcp.tool(annotations={"title": "Save 3DM File", "readOnlyHint": False})
    def rhino_save(args: _SaveIn) -> dict[str, Any]:
        """Write the document to disk."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.io.save", args.model_dump())
        target = registry().save(args.doc_id, args.path, args.version)
        return {
            "summary": {"doc_id": args.doc_id, "path": str(target), "version": args.version},
            "text": f"Saved doc {args.doc_id} to {target}",
        }

    @mcp.tool(annotations={"title": "Export OBJ", "readOnlyHint": False})
    def rhino_export_obj(args: _ExportIn) -> dict[str, Any]:
        """Export selected (or all) objects to a Wavefront OBJ file (mesh-only)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.io.export_obj", args.model_dump())
        handle = registry().get(args.doc_id)
        objs = _resolve_objects(handle, args.object_ids)
        path = Path(args.path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write("# rhino-mcp export\n")
            v_offset = 1
            for obj in objs:
                geom = obj.Geometry
                if isinstance(geom, r3.Mesh):
                    _write_mesh_obj(f, geom, v_offset)
                    v_offset += geom.Vertices.__len__()
        return {"summary": {"path": str(path), "object_count": len(objs)}, "text": f"Wrote {path}"}

    @mcp.tool(annotations={"title": "Export STL", "readOnlyHint": False})
    def rhino_export_stl(args: _ExportIn) -> dict[str, Any]:
        """Export meshes to an ASCII STL file."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.io.export_stl", args.model_dump())
        handle = registry().get(args.doc_id)
        objs = _resolve_objects(handle, args.object_ids)
        path = Path(args.path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write("solid rhino_mcp\n")
            for obj in objs:
                geom = obj.Geometry
                if isinstance(geom, r3.Mesh):
                    _write_mesh_stl(f, geom)
            f.write("endsolid rhino_mcp\n")
        return {"summary": {"path": str(path), "object_count": len(objs)}, "text": f"Wrote {path}"}

    @mcp.tool(annotations={"title": "Import File", "readOnlyHint": False})
    def rhino_import(args: _ExportIn) -> dict[str, Any]:
        """Import an external file into the active document (bridge required for non-3DM)."""
        path = Path(args.path).expanduser().resolve()
        if not path.exists():
            raise not_found_error("file", str(path))
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.io.import", args.model_dump())
        if path.suffix.lower() != ".3dm":
            raise unsupported_in_standalone("rhino_import (non-3DM)")
        handle = registry().open(path)
        return {
            "summary": {"path": str(path), "imported_doc_id": handle.doc_id},
            "text": f"Imported {path} as doc {handle.doc_id}",
        }

    if mode is Mode.STANDALONE:
        return  # bridge-only IO tools below

    @mcp.tool(annotations={"title": "Export STEP", "readOnlyHint": False})
    def rhino_export_step(args: _ExportIn) -> dict[str, Any]:
        """Export to STEP (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_export_step")
        return runtime().require_bridge().call("rhino.io.export_step", args.model_dump())

    @mcp.tool(annotations={"title": "Export IGES", "readOnlyHint": False})
    def rhino_export_iges(args: _ExportIn) -> dict[str, Any]:
        """Export to IGES (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_export_iges")
        return runtime().require_bridge().call("rhino.io.export_iges", args.model_dump())

    @mcp.tool(annotations={"title": "Export DXF", "readOnlyHint": False})
    def rhino_export_dxf(args: _ExportIn) -> dict[str, Any]:
        """Export to DXF (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_export_dxf")
        return runtime().require_bridge().call("rhino.io.export_dxf", args.model_dump())

    @mcp.tool(annotations={"title": "Save Screenshot", "readOnlyHint": False})
    def rhino_screenshot(args: _ScreenshotIn) -> dict[str, Any]:
        """Capture a viewport screenshot (bridge required).

        With ``as_base64=True`` the response includes ``image_base64`` so
        the LLM can inspect the render inline. The PNG is also written to
        ``path`` regardless, for the user to save/share.
        """
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_screenshot")
        result = runtime().require_bridge().call("rhino.io.screenshot", args.model_dump())
        if isinstance(result, dict):
            result.setdefault("mime", args.mime)
        return result

    @mcp.tool(annotations={"title": "Viewport Preview (filtered)", "readOnlyHint": False})
    def rhino_viewport_preview(args: _ViewportPreviewIn) -> dict[str, Any]:
        """Capture a viewport preview restricted to a selection or layer set.

        Spotlights ``selection_ids`` and/or objects on ``layers``; everything
        else is either ghosted (default) or hidden during the capture and
        restored afterwards. Useful for multi-step LLM verification flows
        where only the recently added objects need to be visualised. Bridge
        only.
        """
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_viewport_preview")
        return runtime().require_bridge().call(
            "rhino.io.viewport_preview", args.model_dump()
        )


def _write_mesh_obj(f, mesh: r3.Mesh, v_offset: int) -> None:
    for v in (mesh.Vertices[i] for i in range(mesh.Vertices.__len__())):
        f.write(f"v {v.X} {v.Y} {v.Z}\n")
    for face in (mesh.Faces[i] for i in range(mesh.Faces.__len__())):
        a, b, c, d = face[0], face[1], face[2], face[3]
        if c == d:
            f.write(f"f {v_offset + a} {v_offset + b} {v_offset + c}\n")
        else:
            f.write(f"f {v_offset + a} {v_offset + b} {v_offset + c} {v_offset + d}\n")


def _write_mesh_stl(f, mesh: r3.Mesh) -> None:
    for face in (mesh.Faces[i] for i in range(mesh.Faces.__len__())):
        a, b, c, d = face[0], face[1], face[2], face[3]
        triangles = [(a, b, c)] if c == d else [(a, b, c), (a, c, d)]
        for t in triangles:
            v0 = mesh.Vertices[t[0]]
            v1 = mesh.Vertices[t[1]]
            v2 = mesh.Vertices[t[2]]
            ux, uy, uz = v1.X - v0.X, v1.Y - v0.Y, v1.Z - v0.Z
            vx, vy, vz = v2.X - v0.X, v2.Y - v0.Y, v2.Z - v0.Z
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            length = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
            f.write(f"  facet normal {nx / length} {ny / length} {nz / length}\n")
            f.write("    outer loop\n")
            for v in (v0, v1, v2):
                f.write(f"      vertex {v.X} {v.Y} {v.Z}\n")
            f.write("    endloop\n  endfacet\n")
