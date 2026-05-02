"""Parametric facade — a rectangular array of NURBS panels.

Demonstrates: NURBS curve construction, layer management, rectangular array
transform, and 3DM export. Standalone-only.

Usage:
    RHINO_MCP_FORCE_MODE=standalone uv run python examples/parametric_facade.py
"""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path

os.environ.setdefault("RHINO_MCP_FORCE_MODE", "standalone")

from rhino_mcp.server import build_server  # noqa: E402
from rhino_mcp.utils.registry import Mode  # noqa: E402


async def run(target: Path) -> None:
    mcp, _ = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
    tools = mcp._tool_manager._tools

    async def call(name: str, payload: dict) -> dict:
        return await tools[name].run({"args": payload})

    await call("rhino_layer_create", {"name": "Facade", "color": {"r": 100, "g": 200, "b": 255}})

    # One panel = a degree-3 NURBS curve approximating a sinusoidal ribbon.
    samples = 32
    pts = [
        {
            "x": i / (samples - 1) * 4.0,
            "y": 0.5 * math.sin(2 * math.pi * (i / (samples - 1))),
            "z": 0.0,
        }
        for i in range(samples)
    ]
    panel = await call(
        "rhino_nurbs_curve",
        {"control_points": pts, "degree": 3, "layer": "Facade", "name": "panel"},
    )
    panel_id = panel["summary"]["object_id"]

    array = await call(
        "rhino_array_rectangular",
        {
            "object_ids": [panel_id],
            "count_x": 6,
            "count_y": 1,
            "count_z": 4,
            "spacing_x": 4.0,
            "spacing_y": 1.0,
            "spacing_z": 1.5,
        },
    )
    print(f"Original panel: {panel_id}")
    print(f"Array produced {len(array['summary']['object_ids'])} copies.")

    await call("rhino_save", {"path": str(target), "version": 8})
    print(f"Wrote {target}")


if __name__ == "__main__":
    asyncio.run(run(Path("/tmp/parametric_facade.3dm")))
