"""Surface paneling tools: panelise, UV grid, panel frames.

Bridge-only — requires live Rhino for surface evaluation and paneling.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _PanelizeIn(BaseModel):
    object_id: str = Field(..., description="GUID of the surface to panelize.")
    u_count: int = Field(..., ge=1, le=500, description="Panel divisions in U direction.")
    v_count: int = Field(..., ge=1, le=500, description="Panel divisions in V direction.")
    panel_type: str = Field(
        "quad", description="Panel geometry: 'quad', 'triangle', or 'diamond'.",
    )
    layer: str | None = None


class _UvGridIn(BaseModel):
    object_id: str = Field(..., description="GUID of the surface.")
    u_count: int = Field(..., ge=1, le=500)
    v_count: int = Field(..., ge=1, le=500)
    layer: str | None = None


class _PanelFramesIn(BaseModel):
    object_id: str = Field(..., description="GUID of the surface.")
    u_count: int = Field(..., ge=1, le=500)
    v_count: int = Field(..., ge=1, le=500)
    offset: float = Field(0, description="Normal offset distance for frames.")
    layer: str | None = None


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Panelize Surface"})
    def rhino_panelize_surface(args: _PanelizeIn) -> dict[str, Any]:
        """Subdivide a surface into panels (quad, triangle, or diamond)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_panelize_surface")
        return runtime().require_bridge().call("rhino.panel.panelize", args.model_dump())

    @mcp.tool(annotations={"title": "Create UV Grid"})
    def rhino_create_uv_grid(args: _UvGridIn) -> dict[str, Any]:
        """Create a point grid on a surface at even UV intervals."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_create_uv_grid")
        return runtime().require_bridge().call("rhino.panel.uv_grid", args.model_dump())

    @mcp.tool(annotations={"title": "Create Panel Frames", "readOnlyHint": True})
    def rhino_panel_frames(args: _PanelFramesIn) -> dict[str, Any]:
        """Generate oriented frames (planes) at panel centres for construction."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_panel_frames")
        return runtime().require_bridge().call("rhino.panel.frames", args.model_dump())
