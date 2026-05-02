"""Viewport and display tools (all bridge-only — rhino3dm has no viewport)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

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
