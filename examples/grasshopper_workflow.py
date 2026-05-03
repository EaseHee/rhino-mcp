"""Grasshopper workflow — bridge-only end-to-end demo.

Requires: Rhino 8 running with Grasshopper open and the
``RhinoMCPBridge.rhp`` C# plugin loaded (see docs/en/installation.md).

Steps:
  1. Open a parametric definition.
  2. Sweep a 'span' slider through a range of values.
  3. After each step, bake the named output component to a per-iteration layer.
  4. Save the canvas back to disk so the new bake history is preserved.

Usage:
    RHINO_MCP_FORCE_MODE=bridge uv run python examples/grasshopper_workflow.py /work/wing.gh
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("RHINO_MCP_FORCE_MODE", "bridge")

from rhino_mcp.server import build_server  # noqa: E402


async def run(gh_path: Path) -> None:
    # build_server consults the auto-detector; if no bridge is reachable it
    # raises ToolError with a clear hint.
    mcp, count = build_server()
    print(f"Bridge connected; {count} tools registered.")
    tools = mcp._tool_manager._tools

    async def call(name: str, payload: dict | None = None) -> dict:
        return await tools[name].run({"args": payload or {}})

    await call("gh_open_file", {"path": str(gh_path)})

    # Discover the slider and output component by nickname.
    listing = await call("gh_component_list", {"filter": ""})
    span_id = next(
        c["id"] for c in listing.get("summary", {}).get("components", []) if c["nick"] == "span"
    )
    out_id = next(
        c["id"] for c in listing.get("summary", {}).get("components", []) if c["nick"] == "out"
    )

    for span in (8.0, 10.0, 12.0, 14.0, 16.0):
        await call("gh_set_slider", {"component_id": span_id, "value": span})
        await call("gh_run", {"new_solution": True})
        await call(
            "gh_bake_to_rhino",
            {"component_ids": [out_id], "layer": f"Bake/span={int(span)}"},
        )
        print(f"Baked span={span}")

    await call("gh_save_file", {"path": str(gh_path)})
    print("Saved canvas.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: grasshopper_workflow.py <wing.gh>", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(run(Path(sys.argv[1])))
