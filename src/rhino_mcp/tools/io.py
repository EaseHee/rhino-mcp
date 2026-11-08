"""File I/O tools (open/save 3DM, export OBJ/STL/Draco, screenshot, import)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.document import registry
from rhino_mcp.tools._helpers import (
    _MIME_TO_FORMAT,
    CaptureImageArgs,
    CaptureResult,
    capture_content,
    capture_params,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import (
    ErrorCategory,
    ToolError,
    not_found_error,
    parameter_error,
    unsupported_in_standalone,
)
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


class _ExportDracoIn(_DocArg):
    path: str = Field(..., description="Absolute output path for the .drc file.")
    object_ids: list[str] | None = Field(
        None,
        description=(
            "Mesh object GUIDs to compress; default = every mesh in the document. "
            "Multiple meshes are merged into a single Draco mesh."
        ),
    )
    compression_level: Annotated[int, Field(ge=0, le=10)] = Field(
        7, description="Draco encoder speed/size trade-off (0 = fastest, 10 = smallest)."
    )
    position_quantization_bits: Annotated[int, Field(ge=1, le=30)] = Field(
        14, description="Quantization bits for vertex positions (higher = more precise)."
    )
    include_normals: bool = True
    include_texture_coordinates: bool = True
    include_vertex_colors: bool = True


class _ScreenshotIn(CaptureImageArgs, _DocArg):
    path: str | None = Field(
        None,
        description=(
            "Absolute output path for the full-size file (format from the extension). "
            "When omitted the bridge captures to a temp file and deletes it."
        ),
    )
    width: Annotated[int, Field(ge=64, le=8192, description="Image width in pixels.")] = 1280
    height: Annotated[int, Field(ge=64, le=8192, description="Image height in pixels.")] = 720
    as_base64: bool | None = Field(
        None,
        description=(
            "Deprecated alias of ``include_image``. False together with ``path`` "
            "returns only the summary."
        ),
    )
    mime: str | None = Field(
        None,
        description="Deprecated alias of ``format`` ('image/png' or 'image/jpeg').",
    )


class _ViewportPreviewIn(CaptureImageArgs, _DocArg):
    path: str | None = Field(
        None,
        description="Absolute output path for the full-size file; temp file when omitted.",
    )
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

    @mcp.tool(annotations={"title": "Export Draco (.drc)", "readOnlyHint": False})
    def rhino_export_draco(args: _ExportDracoIn) -> dict[str, Any]:
        """Compress mesh objects to a Google Draco ``.drc`` file (standalone, rhino3dm).

        Exports one mesh by id, a list of meshes, or every mesh in the
        document; several meshes are merged into one Draco mesh. Non-mesh
        objects are skipped (rhino3dm cannot tessellate Breps).
        """
        if runtime().mode is Mode.BRIDGE:
            raise ToolError(
                ErrorCategory.UNSUPPORTED,
                "Tool 'rhino_export_draco' runs on the standalone rhino3dm document only.",
                "In bridge mode use Rhino's own Draco exporter via rhino_execute_python "
                "(rs.Command('_-Export \"<path>.drc\" _Enter')).",
                details={"tool": "rhino_export_draco"},
            )
        handle = registry().get(args.doc_id)
        objs = _resolve_objects(handle, args.object_ids)
        meshes: list[r3.Mesh] = [g for obj in objs if isinstance(g := obj.Geometry, r3.Mesh)]
        skipped = len(objs) - len(meshes)
        if not meshes:
            raise parameter_error("object_ids", "no mesh objects to export", "mesh object GUIDs")
        if args.object_ids and skipped:
            raise parameter_error(
                "object_ids", f"{skipped} of the given objects are not meshes", "mesh object GUIDs"
            )
        merged = r3.Mesh()
        for mesh in meshes:
            merged.Append(mesh)
        options = r3.DracoCompressionOptions()
        options.CompressionLevel = args.compression_level
        options.PositionQuantizationBits = args.position_quantization_bits
        options.IncludeNormals = args.include_normals
        options.IncludeTextureCoordinates = args.include_texture_coordinates
        options.IncludeVertexColors = args.include_vertex_colors
        draco = r3.DracoCompression.Compress(merged, options)
        if draco is None:
            raise ToolError(
                ErrorCategory.INTERNAL,
                "Draco compression failed.",
                "Check that the meshes are valid and not empty.",
            )
        path = Path(args.path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not draco.Write(str(path)):
            raise ToolError(
                ErrorCategory.INTERNAL,
                f"Could not write Draco file: {path}",
                "Check that the directory is writable.",
            )
        size = path.stat().st_size
        return {
            "summary": {
                "path": str(path),
                "mesh_count": len(meshes),
                "skipped_non_mesh": skipped,
                "vertex_count": len(merged.Vertices),  # type: ignore[arg-type]
                "face_count": merged.Faces.Count,
                "bytes": size,
            },
            "text": f"Wrote {len(meshes)} mesh(es) to {path} ({size} bytes, Draco)",
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

    @mcp.tool(
        annotations={"title": "Save Screenshot", "readOnlyHint": False},
        structured_output=False,
    )
    def rhino_screenshot(args: _ScreenshotIn) -> CaptureResult:
        """Capture a viewport screenshot (bridge required).

        Returns MCP image content (JPEG, at most ``max_width`` px wide by
        default) plus a summary, so the model sees the viewport directly.
        When ``path`` is given the full-size file is written there too;
        ``include_image=False`` (or legacy ``as_base64=False``) with a
        ``path`` returns only the summary.
        """
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_screenshot")
        if args.mime is not None:
            fmt = _MIME_TO_FORMAT.get(args.mime.lower())
            if fmt is None:
                raise parameter_error("mime", f"unsupported {args.mime!r}", "image/png, image/jpeg")
            args = args.model_copy(update={"format": fmt})
        include = args.include_image and args.as_base64 is not False
        # Without a file there is nothing else to return, so the image is always sent.
        include = include or not args.path
        params = capture_params(args, include)
        result = runtime().require_bridge().call("rhino.io.screenshot", params)
        return capture_content(result, include)

    @mcp.tool(
        annotations={"title": "Viewport Preview (filtered)", "readOnlyHint": False},
        structured_output=False,
    )
    def rhino_viewport_preview(args: _ViewportPreviewIn) -> CaptureResult:
        """Capture a viewport preview restricted to a selection or layer set.

        Spotlights ``selection_ids`` and/or objects on ``layers``; everything
        else is either ghosted (default) or hidden during the capture and
        restored afterwards. Selection and visibility are restored, so the
        document is left unchanged. Returns MCP image content plus a summary
        (see ``rhino_screenshot`` for the image controls). Bridge only.
        """
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_viewport_preview")
        include = args.include_image or not args.path
        params = capture_params(args, include)
        result = runtime().require_bridge().call("rhino.io.viewport_preview", params)
        return capture_content(result, include)


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
