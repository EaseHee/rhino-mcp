"""Viewport and display tools (all bridge-only — rhino3dm has no viewport)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import (
    CaptureImageArgs,
    CaptureResult,
    capture_content,
    capture_params,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _ViewSetIn(_DocArg):
    name: str = Field(..., description="Named view to activate.")


class _ZoomIn(_DocArg):
    object_ids: list[str] | None = Field(None, description="Restrict zoom; default = all visible objects.")


class _NamedViewSaveIn(_DocArg):
    name: str = Field(..., min_length=1)


class _DisplayModeIn(_DocArg):
    mode: str = Field(..., description="Display-mode name (e.g. 'Wireframe', 'Shaded', 'Rendered').")


class _TurntableIn(_DocArg):
    output_path: str
    frames: Annotated[int, Field(ge=2, le=720)] = 120
    width: Annotated[int, Field(ge=64, le=8192)] = 1280
    height: Annotated[int, Field(ge=64, le=8192)] = 720


class _ZoomObjectIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=500)


class _ZoomLayerIn(_DocArg):
    layer: str = Field(..., min_length=1, description="Full layer path.")


class _CaptureViewportIn(CaptureImageArgs, _DocArg):
    view_name: str | None = Field(
        None,
        description="Viewport to capture; defaults to the active viewport.",
    )
    width: Annotated[int, Field(ge=0, le=8192)] = 0
    height: Annotated[int, Field(ge=0, le=8192)] = 0
    transparent_bg: bool = False
    output_path: str | None = Field(
        None,
        description=(
            "Full-size PNG path; when omitted no file is written unless "
            "``include_image`` is False (then a temp file path is returned)."
        ),
    )


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Activate Named View", "readOnlyHint": False})
    def rhino_view_set(args: _ViewSetIn) -> dict[str, Any]:
        """Activate a saved named view."""
        return runtime().require_bridge().call("rhino.display.view_set", args.model_dump())

    @mcp.tool(annotations={"title": "Zoom to Extents", "readOnlyHint": False})
    def rhino_zoom_extent(args: _ZoomIn) -> dict[str, Any]:
        """Zoom the active view to the extent of selected (or all) objects."""
        return runtime().require_bridge().call("rhino.display.zoom_extent", args.model_dump())

    @mcp.tool(annotations={"title": "Save Named View", "readOnlyHint": False})
    def rhino_named_view_save(args: _NamedViewSaveIn) -> dict[str, Any]:
        """Save the current camera as a named view."""
        return runtime().require_bridge().call("rhino.display.named_view_save", args.model_dump())

    @mcp.tool(annotations={"title": "Set Display Mode", "readOnlyHint": False})
    def rhino_display_mode_set(args: _DisplayModeIn) -> dict[str, Any]:
        """Switch the active viewport's display mode."""
        return runtime().require_bridge().call("rhino.display.mode_set", args.model_dump())

    @mcp.tool(annotations={"title": "Render Turntable Animation", "readOnlyHint": False})
    def rhino_turntable(args: _TurntableIn) -> dict[str, Any]:
        """Render a turntable animation to ``output_path`` (PNG sequence or GIF)."""
        return runtime().require_bridge().call("rhino.display.turntable", args.model_dump())

    @mcp.tool(annotations={"title": "Zoom to Objects", "readOnlyHint": False})
    def rhino_zoom_object(args: _ZoomObjectIn) -> dict[str, Any]:
        """Zoom the active viewport to fit the given object ids exactly."""
        return runtime().require_bridge().call("rhino.display.zoom_object", args.model_dump())

    @mcp.tool(annotations={"title": "Zoom to Layer", "readOnlyHint": False})
    def rhino_zoom_layer(args: _ZoomLayerIn) -> dict[str, Any]:
        """Zoom the active viewport to fit every object on ``layer``."""
        return runtime().require_bridge().call("rhino.display.zoom_layer", args.model_dump())

    @mcp.tool(
        annotations={"title": "Capture Viewport Image", "readOnlyHint": False, "idempotentHint": False},
        structured_output=False,
    )
    def rhino_viewport_image(args: _CaptureViewportIn) -> CaptureResult:
        """Capture the viewport pixels and return them as MCP image content.

        Lightweight alternative to ``rhino_render_to_file`` — no render engine
        is invoked, just a viewport bitmap dump. Use 0 for ``width``/``height``
        to inherit the on-screen viewport size; the inline image is then
        downscaled to ``max_width`` (default 1024, JPEG). Pass ``output_path``
        to also keep the full-size PNG.
        """
        warnings: list[str] = []
        if args.transparent_bg and args.format == "jpeg":
            if "format" in args.model_fields_set:
                warnings.append(
                    "format='jpeg' has no alpha channel; the transparent background "
                    "is flattened onto white in the inline image (use format='png')."
                )
            else:
                # Keep transparency when the caller did not pick a format.
                args = args.model_copy(update={"format": "png"})
        include = args.include_image
        params = capture_params(args, include)
        result = runtime().require_bridge().call("rhino.display.capture_viewport", params)
        if warnings and isinstance(result, dict):
            result.setdefault("warnings", []).extend(warnings)
        return capture_content(result, include)
