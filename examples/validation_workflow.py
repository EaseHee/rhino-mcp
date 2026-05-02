"""Geometry validation workflow — diagnose before exporting.

Demonstrates the v0.2.0 validation tools (rhino_validate_brep,
rhino_curve_continuity, rhino_report_mesh_health) on a small composition.
Useful as a pre-flight check before booleans, exports, or fabrication.

Runs in standalone mode — no Rhino install required.

Usage:
    RHINO_MCP_FORCE_MODE=standalone uv run python examples/validation_workflow.py
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("RHINO_MCP_FORCE_MODE", "standalone")

from rhino_mcp.server import build_server  # noqa: E402
from rhino_mcp.utils.registry import Mode  # noqa: E402


async def run() -> int:
    mcp, count = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
    print(f"Registered {count} tool modules.")
    tools = mcp._tool_manager._tools

    async def call(name: str, payload: dict) -> dict:
        return await tools[name].run({"args": payload})

    # --- Build a closed solid + an open curve + a small mesh -------------
    box = await call(
        "rhino_box",
        {
            "corner": {"x": 0, "y": 0, "z": 0},
            "size_x": 10.0,
            "size_y": 10.0,
            "size_z": 10.0,
            "name": "Block",
        },
    )
    line = await call(
        "rhino_line",
        {"start": {"x": 0, "y": 0, "z": 0}, "end": {"x": 25, "y": 0, "z": 0}, "name": "Path"},
    )
    mesh_box = await call(
        "rhino_mesh_box",
        {
            "corner": {"x": 20, "y": 0, "z": 0},
            "size_x": 5.0,
            "size_y": 5.0,
            "size_z": 5.0,
            "name": "MeshBlock",
        },
    )

    bid = box["summary"]["object_id"]
    lid = line["summary"]["object_id"]
    mid = mesh_box["summary"]["object_id"]

    # --- Run validation -------------------------------------------------
    brep_report = await call("rhino_validate_brep", {"object_id": bid})
    curve_report = await call("rhino_curve_continuity", {"object_id": lid})
    mesh_report = await call("rhino_report_mesh_health", {"object_id": mid})

    print("Brep:")
    print(f"  is_valid={brep_report['summary']['is_valid']}")
    print(f"  is_solid={brep_report['summary']['is_solid']}")
    print(f"  is_manifold={brep_report['summary']['is_manifold']}")
    print(f"  faces={brep_report['summary']['face_count']}, edges={brep_report['summary']['edge_count']}")
    if brep_report["summary"]["issues"]:
        print(f"  issues: {brep_report['summary']['issues']}")

    print("Curve:")
    print(
        f"  closed={curve_report['summary']['is_closed']}, "
        f"planar={curve_report['summary']['is_planar']}, "
        f"spans={curve_report['summary']['span_count']}"
    )

    print("Mesh:")
    print(
        f"  is_valid={mesh_report['summary']['is_valid']}, "
        f"closed={mesh_report['summary']['is_closed']}, "
        f"vertices={mesh_report['summary']['vertex_count']}, "
        f"faces={mesh_report['summary']['face_count']}"
    )

    # Aggregate exit code: 0 if everything healthy, 1 otherwise.
    issues = (
        len(brep_report["summary"]["issues"])
        + len(curve_report["summary"]["issues"])
        + len(mesh_report["summary"]["issues"])
    )
    if issues:
        print(f"\n{issues} validation issue(s) found.")
        return 1
    print("\nAll geometry validates clean.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
