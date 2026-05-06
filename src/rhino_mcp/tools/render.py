"""Render automation tools — camera, light, render-output (bridge only).

Standalone has no viewport / renderer, so every tool here is bridge gated.
The handlers wrap RhinoCommon's ``RhinoView``, ``RhinoDoc.Lights``, and
the active render content engine (Rhino Render / Cycles / V-Ray when
installed).

Tool catalogue:
- rhino_camera_set — position + target + lens length on the active
  view (or a named view).
- rhino_light_add — point / spot / directional / rectangular lights
  with intensity and colour.
- rhino_render_setup — resolution, samples, render engine, output
  path, alpha matte.
- rhino_render_to_file — execute the render with the current setup
  and write to disk.
- rhino_turntable_render — render a frame sequence around the model
  (front-end for a parametric camera sweep).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import bridge_call, require_bridge_only
from rhino_mcp.utils.error_handling import parameter_error
from rhino_mcp.utils.registry import Mode

_LIGHT_KINDS = ("point", "spot", "directional", "rectangular", "linear")
_RENDER_ENGINES = ("rhino", "cycles", "raytraced", "vray", "active")


class _CameraSetIn(BaseModel):
    location: Point3dModel
    target: Point3dModel
    lens_length_mm: Annotated[float, Field(gt=0, le=2000)] = 50.0
    view_name: str | None = Field(
        None,
        description="Optional named view to update; defaults to the active viewport.",
    )


class _LightAddIn(BaseModel):
    kind: str = Field(
        "point", description="Light kind: point / spot / directional / rectangular / linear."
    )
    location: Point3dModel | None = Field(None)
    target: Point3dModel | None = Field(None)
    intensity: Annotated[float, Field(ge=0.0, le=10000.0)] = 1.0
    color: tuple[int, int, int] = Field((255, 255, 255))
    spot_angle_deg: Annotated[float, Field(gt=0, lt=180)] = 45.0
    width: Annotated[float, Field(gt=0)] = 1.0
    length: Annotated[float, Field(gt=0)] = 1.0
    name: str | None = Field(None)
    layer: str | None = Field(None)


class _RenderSetupIn(BaseModel):
    width: Annotated[int, Field(ge=64, le=8192)] = 1920
    height: Annotated[int, Field(ge=64, le=8192)] = 1080
    samples: Annotated[int, Field(ge=1, le=20000)] = 200
    engine: str = Field(
        "active",
        description="Rhino render engine: rhino / cycles / raytraced / vray / active.",
    )
    transparent_background: bool = Field(False)
    output_path: str | None = Field(
        None,
        description="If set, render-to-file uses this path by default.",
    )


class _RenderToFileIn(BaseModel):
    output_path: str = Field(..., description="Absolute output image path (.png recommended).")
    width: Annotated[int, Field(ge=64, le=8192)] | None = Field(None)
    height: Annotated[int, Field(ge=64, le=8192)] | None = Field(None)
    samples: Annotated[int, Field(ge=1, le=20000)] | None = Field(None)
    transparent_background: bool | None = Field(None)


class _RenderQueueFrame(BaseModel):
    output_path: str = Field(..., description="Absolute path for this frame's PNG.")
    width: Annotated[int, Field(ge=64, le=8192)] = 1920
    height: Annotated[int, Field(ge=64, le=8192)] = 1080
    view: str | None = Field(None, description="Optional named view (uses active viewport when None).")


class _RenderQueueSubmitIn(BaseModel):
    frames: list[_RenderQueueFrame] = Field(..., min_length=1, max_length=1024)


class _RenderQueueJobIdIn(BaseModel):
    job_id: str = Field(..., description="GUID returned by ``rhino_render_queue_submit``.")


class _RenderQueueListIn(BaseModel):
    pass


class _TurntableRenderIn(BaseModel):
    output_dir: str = Field(..., description="Directory the frame sequence is written into.")
    frame_count: Annotated[int, Field(ge=4, le=720)] = 36
    radius: Annotated[float, Field(gt=0)] = 50.0
    height: Annotated[float, Field(ge=-10000.0, le=10000.0)] = 20.0
    target: Point3dModel = Field(default_factory=lambda: Point3dModel(x=0.0, y=0.0, z=0.0))
    width: Annotated[int, Field(ge=64, le=8192)] = 1280
    render_height: Annotated[int, Field(ge=64, le=8192)] = 720
    samples: Annotated[int, Field(ge=1, le=20000)] = 100


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Set Camera", "readOnlyHint": False})
    def rhino_camera_set(args: _CameraSetIn) -> dict[str, Any]:
        """Position the active viewport's camera (location + target + lens length)."""
        require_bridge_only("rhino_camera_set")
        return bridge_call("rhino.render.camera_set", args.model_dump())

    @mcp.tool(annotations={"title": "Add Light", "readOnlyHint": False})
    def rhino_light_add(args: _LightAddIn) -> dict[str, Any]:
        """Add a point / spot / directional / rectangular / linear light to the document."""
        require_bridge_only("rhino_light_add")
        if args.kind not in _LIGHT_KINDS:
            raise parameter_error(
                "kind",
                f"unknown light kind '{args.kind}'",
                allowed=", ".join(_LIGHT_KINDS),
            )
        return bridge_call("rhino.render.light_add", args.model_dump())

    @mcp.tool(annotations={"title": "Configure Render Setup", "readOnlyHint": False})
    def rhino_render_setup(args: _RenderSetupIn) -> dict[str, Any]:
        """Set render resolution / samples / engine / transparency on the active render context."""
        require_bridge_only("rhino_render_setup")
        if args.engine not in _RENDER_ENGINES:
            raise parameter_error(
                "engine",
                f"unknown render engine '{args.engine}'",
                allowed=", ".join(_RENDER_ENGINES),
            )
        return bridge_call("rhino.render.setup", args.model_dump())

    @mcp.tool(annotations={"title": "Render To File", "readOnlyHint": False})
    def rhino_render_to_file(args: _RenderToFileIn) -> dict[str, Any]:
        """Execute the configured render and write the result to ``output_path``."""
        require_bridge_only("rhino_render_to_file")
        return bridge_call("rhino.render.to_file", args.model_dump())

    @mcp.tool(annotations={"title": "Turntable Render", "readOnlyHint": False})
    def rhino_turntable_render(args: _TurntableRenderIn) -> dict[str, Any]:
        """Render a turntable sequence (camera orbits around ``target``) to ``output_dir``."""
        require_bridge_only("rhino_turntable_render")
        return bridge_call("rhino.render.turntable", args.model_dump())

    @mcp.tool(annotations={"title": "Render Queue: Submit", "readOnlyHint": False})
    def rhino_render_queue_submit(args: _RenderQueueSubmitIn) -> dict[str, Any]:
        """Submit a frame sequence to the bridge render queue (bridge only).

        Returns a ``job_id`` immediately while frames are captured on a
        background worker. Use ``rhino_render_queue_status`` to poll
        progress and ``rhino_render_queue_cancel`` to interrupt. The v0.5
        backend captures viewport frames (``_-ViewCaptureToFile``); true
        photo-realistic engine integration is on the roadmap.
        """
        require_bridge_only("rhino_render_queue_submit")
        return bridge_call("rhino.render.queue.submit", args.model_dump())

    @mcp.tool(annotations={"title": "Render Queue: Status", "readOnlyHint": True, "idempotentHint": True})
    def rhino_render_queue_status(args: _RenderQueueJobIdIn) -> dict[str, Any]:
        """Inspect a queued render job's status, progress, and completed frames."""
        require_bridge_only("rhino_render_queue_status")
        return bridge_call("rhino.render.queue.status", args.model_dump())

    @mcp.tool(annotations={"title": "Render Queue: Cancel", "readOnlyHint": False})
    def rhino_render_queue_cancel(args: _RenderQueueJobIdIn) -> dict[str, Any]:
        """Cancel a running or queued render job."""
        require_bridge_only("rhino_render_queue_cancel")
        return bridge_call("rhino.render.queue.cancel", args.model_dump())

    @mcp.tool(annotations={"title": "Render Queue: List", "readOnlyHint": True, "idempotentHint": True})
    def rhino_render_queue_list(args: _RenderQueueListIn) -> dict[str, Any]:
        """List recent render jobs and their progress."""
        require_bridge_only("rhino_render_queue_list")
        return bridge_call("rhino.render.queue.list", args.model_dump())
