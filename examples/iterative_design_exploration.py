"""Iterative design exploration — Grasshopper template + parameter sweep.

Demonstrates the v0.2.0 GH templates flow: list → load → bind sliders →
run → bake → screenshot, repeated across a small sweep of values so the
user can compare variants side by side.

BRIDGE-ONLY: requires a live Rhino 8 with the rhino-mcp plugin
loaded. The first call (gh_template_list) reads the manifest and works
in any mode, but loading and running the templates requires the bridge.

Usage:
    # In a separate terminal, start Rhino 8 + bridge plugin first.
    uv run python examples/iterative_design_exploration.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

os.environ.setdefault("RHINO_MCP_FORCE_MODE", "bridge")

from rhino_mcp.server import build_server  # noqa: E402


async def run() -> None:
    mcp, count = build_server()
    print(f"Registered {count} tool modules.")
    tools = mcp._tool_manager._tools

    async def call(name: str, payload: dict) -> dict:
        return await tools[name].run({"args": payload})

    # --- Discover the catalogue ------------------------------------------
    catalog = await call("gh_template_list", {})
    available = [t for t in catalog["summary"]["templates"] if t["available"]]
    if not available:
        print("No template binaries shipped yet. Place .gh files alongside")
        print("src/rhino_mcp/data/gh_templates/manifest.json and re-run.")
        return
    print(f"Available templates: {[t['name'] for t in available]}")

    # --- Load panel_grid -------------------------------------------------
    loaded = await call(
        "gh_load_template",
        {"name": "panel_grid", "canvas_target": "active"},
    )
    template_id = loaded["summary"]["template_id"]
    print(f"Loaded panel_grid as {template_id}")

    # --- Sweep panel widths: 0.6, 0.8, 1.0, 1.2 m -----------------------
    out_dir = Path("/tmp/rhino_mcp_sweep")
    out_dir.mkdir(parents=True, exist_ok=True)
    for variant_idx, panel_w in enumerate([0.6, 0.8, 1.0, 1.2]):
        await call(
            "gh_bind_template_parameter",
            {"template_id": template_id, "parameter": "panel_w", "value": panel_w},
        )
        await call(
            "gh_bind_template_parameter",
            {"template_id": template_id, "parameter": "count_x", "value": 12},
        )
        await call(
            "gh_run_template",
            {"template_id": template_id, "bake": True, "layer": f"study::v{variant_idx:02d}"},
        )
        # Visual evidence of the variant
        await call("rhino_zoom_extent", {})
        await call(
            "rhino_named_view_save",
            {"name": f"checkpoint/v{variant_idx:02d}_w{panel_w:.2f}m"},
        )
        snap = await call(
            "rhino_screenshot",
            {
                "path": str(out_dir / f"v{variant_idx:02d}_w{panel_w:.2f}m.png"),
                "width": 1280,
                "height": 720,
                "as_base64": False,
            },
        )
        print(f"v{variant_idx:02d} panel_w={panel_w}m → {snap['summary'].get('path')}")

    print(f"Sweep complete. Frames in {out_dir}")


if __name__ == "__main__":
    asyncio.run(run())
