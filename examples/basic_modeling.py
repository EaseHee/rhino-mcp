"""Basic standalone modelling example.

Builds a small composition (sphere + box + circle) in an in-memory rhino3dm
document and writes it to a 3DM file. Runs without Rhino installed.

Usage:
    RHINO_MCP_FORCE_MODE=standalone uv run python examples/basic_modeling.py /tmp/basic.3dm
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("RHINO_MCP_FORCE_MODE", "standalone")

from rhino_mcp.server import build_server  # noqa: E402
from rhino_mcp.utils.registry import Mode  # noqa: E402


async def run(target: Path) -> None:
    mcp, count = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
    print(f"Registered {count} tools.")
    tools = mcp._tool_manager._tools

    async def call(name: str, payload: dict) -> dict:
        return await tools[name].run({"args": payload})

    await call("rhino_layer_create", {"name": "Solids", "color": {"r": 200, "g": 80, "b": 80}})
    await call("rhino_layer_create", {"name": "Curves", "color": {"r": 80, "g": 80, "b": 200}})

    sphere = await call(
        "rhino_sphere",
        {"center": {"x": 0, "y": 0, "z": 0}, "radius": 5.0, "layer": "Solids"},
    )
    box = await call(
        "rhino_box",
        {
            "corner": {"x": 8, "y": -2, "z": 0},
            "size_x": 4.0,
            "size_y": 4.0,
            "size_z": 4.0,
            "layer": "Solids",
        },
    )
    circle = await call(
        "rhino_circle",
        {"center": {"x": 0, "y": 10, "z": 0}, "radius": 3.5, "layer": "Curves"},
    )

    await call("rhino_save", {"path": str(target), "version": 8})
    print(f"sphere id={sphere['summary']['object_id']}")
    print(f"box    id={box['summary']['object_id']}")
    print(f"circle id={circle['summary']['object_id']}")
    print(f"Wrote {target}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/basic.3dm")
    asyncio.run(run(out))
