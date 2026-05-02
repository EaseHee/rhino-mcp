"""Grasshopper canvas-level operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode


class _OpenIn(BaseModel):
    path: str = Field(..., description="Absolute path to a .gh / .ghx file.")


class _SaveIn(BaseModel):
    path: str | None = Field(None, description="Path to save to; defaults to the open file.")


class _NewIn(BaseModel):
    name: str = Field("untitled", description="Document name.")


class _BakeIn(BaseModel):
    component_ids: list[str] = Field(..., min_length=1, description="Components whose output to bake.")
    layer: str | None = Field(None, description="Target Rhino layer (created if absent).")


class _RunIn(BaseModel):
    new_solution: bool = Field(True, description="Force a fresh solution.")


class _PreviewIn(BaseModel):
    component_ids: list[str] | None = Field(None)
    enabled: bool = Field(...)


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "GH: Open File", "readOnlyHint": False})
    def gh_open_file(args: _OpenIn) -> dict[str, Any]:
        """Open a Grasshopper definition."""
        return runtime().require_bridge().call("gh.canvas.open", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Save File", "readOnlyHint": False})
    def gh_save_file(args: _SaveIn) -> dict[str, Any]:
        """Save the active Grasshopper definition."""
        return runtime().require_bridge().call("gh.canvas.save", args.model_dump())

    @mcp.tool(annotations={"title": "GH: New Canvas", "readOnlyHint": False})
    def gh_new_canvas(args: _NewIn) -> dict[str, Any]:
        """Create a fresh empty Grasshopper canvas."""
        return runtime().require_bridge().call("gh.canvas.new", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Run Solution", "readOnlyHint": False})
    def gh_run(args: _RunIn) -> dict[str, Any]:
        """Run the current solution."""
        return runtime().require_bridge().call("gh.canvas.run", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Reset", "readOnlyHint": False, "destructiveHint": True})
    def gh_reset() -> dict[str, Any]:
        """Reset the canvas (clear cached solution)."""
        return runtime().require_bridge().call("gh.canvas.reset", {})

    @mcp.tool(annotations={"title": "GH: Toggle Preview", "readOnlyHint": False})
    def gh_preview_toggle(args: _PreviewIn) -> dict[str, Any]:
        """Toggle preview on/off for a list of components (or all)."""
        return runtime().require_bridge().call("gh.canvas.preview_toggle", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Bake to Rhino", "readOnlyHint": False})
    def gh_bake_to_rhino(args: _BakeIn) -> dict[str, Any]:
        """Bake the output of one or more components into the active Rhino document."""
        return runtime().require_bridge().call("gh.canvas.bake", args.model_dump())
