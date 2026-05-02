"""Architectural massing example — site grid + stacked floors.

Demonstrates the v0.2.0 composition tools (rhino_place_grid, rhino_stack_floors)
plus document-hygiene setup (units, layer tree, user_text metadata) on a
plausible architectural prototype: a 4×3 array of building plots, each
populated with a 6-storey shoebox and tagged with phase/material metadata.

Runs in standalone mode — no Rhino install required.

Usage:
    RHINO_MCP_FORCE_MODE=standalone uv run python examples/architectural_massing.py /tmp/massing.3dm
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
    print(f"Registered {count} tool modules.")
    tools = mcp._tool_manager._tools

    async def call(name: str, payload: dict) -> dict:
        return await tools[name].run({"args": payload})

    # --- Document hygiene first (BIM authoring discipline) -----------------
    await call("rhino_document_units_set", {"units": "m", "scale_existing": False})
    await call("rhino_tolerance_set", {"absolute": 0.001, "angle_degrees": 0.5})
    await call("rhino_layer_create", {"name": "Site", "color": {"r": 120, "g": 160, "b": 120}})
    await call("rhino_layer_create", {"name": "Arch::Mass::Proposed", "color": {"r": 200, "g": 200, "b": 200}})

    # --- Single base plot (2-D footprint as a closed rectangle) -----------
    base = await call(
        "rhino_rectangle",
        {
            "corner": {"x": 0, "y": 0, "z": 0},
            "width": 24.0,
            "height": 16.0,
            "layer": "Site",
            "name": "PlotBase",
        },
    )
    print(f"Base plot id={base['summary']['object_id']}")

    # --- Site grid: 4 plots × 3 rows, 30 m × 22 m pitch -------------------
    site_grid = await call(
        "rhino_place_grid",
        {
            "source_object_id": base["summary"]["object_id"],
            "base_point": {"x": 0, "y": 0, "z": 0},
            "count_x": 4,
            "count_y": 3,
            "spacing_x": 30.0,
            "spacing_y": 22.0,
            "skip_origin": True,
            "name_prefix": "Plot",
        },
    )
    print(f"Site grid: {len(site_grid['summary']['object_ids'])} cell copies")

    # --- A typical massing block (one shoebox; will stack into floors) ----
    block = await call(
        "rhino_box",
        {
            "corner": {"x": 4, "y": 4, "z": 0},
            "size_x": 16.0,
            "size_y": 8.0,
            "size_z": 3.5,
            "layer": "Arch::Mass::Proposed",
            "name": "F0_Slab",
        },
    )
    bid = block["summary"]["object_id"]
    print(f"Ground-floor block id={bid}")

    # --- Stack 5 additional floors above ground (6 storeys total) ---------
    floors = await call(
        "rhino_stack_floors",
        {
            "source_object_id": bid,
            "floor_count": 5,
            "floor_height": 3.5,
            "name_prefix": "F",
        },
    )
    print(f"Stacked {len(floors['summary']['object_ids'])} floor copies")

    # --- Tag the ground-floor block with BIM metadata ---------------------
    for key, value in (
        ("function", "office"),
        ("material", "concrete_frame"),
        ("phase", "proposed"),
        ("revision", "A.01"),
    ):
        await call("rhino_set_user_text", {"object_id": bid, "key": key, "value": value})

    # --- Validate the building block before save --------------------------
    valid = await call("rhino_validate_brep", {"object_id": bid})
    print(
        "Block validation: "
        f"valid={valid['summary']['is_valid']} "
        f"solid={valid['summary']['is_solid']} "
        f"manifold={valid['summary']['is_manifold']}"
    )

    summary = await call("rhino_document_summary", {})
    print(
        f"Document: {summary['summary']['total_objects']} objects, "
        f"{summary['summary']['layer_count']} layers, "
        f"units={summary['summary']['units']}, "
        f"layer_tree_depth={summary['summary']['layer_tree_depth']}"
    )

    await call("rhino_save", {"path": str(target), "version": 8})
    print(f"Wrote {target}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/massing.3dm")
    asyncio.run(run(out))
