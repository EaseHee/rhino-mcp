"""Freeform canopy example — sections → skin → panel classify → fabricate.

Builds a contemporary non-rectilinear canopy by interpolating
between varying-radius arc sections, panelises the resulting skin on a
U×V grid, and reports per-panel curvature classes plus a developability
score. Runs entirely in standalone mode — no Rhino install required.

Usage:
    RHINO_MCP_FORCE_MODE=standalone uv run python examples/freeform_canopy.py /tmp/canopy.3dm
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("RHINO_MCP_FORCE_MODE", "standalone")

from rhino_mcp.server import build_server  # noqa: E402
from rhino_mcp.utils.registry import Mode  # noqa: E402


async def run(target: Path) -> int:
    mcp, count = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
    print(f"Registered {count} tool modules.")
    tools = mcp._tool_manager._tools

    async def call(name: str, payload: dict) -> dict:
        return await tools[name].run({"args": payload})

    # --- Document hygiene -------------------------------------------------
    await call("rhino_document_units_set", {"units": "m", "scale_existing": False})
    await call("rhino_tolerance_set", {"absolute": 0.001, "angle_degrees": 0.5})
    await call("rhino_layer_create", {"name": "Sections", "color": {"r": 80, "g": 120, "b": 200}})
    await call("rhino_layer_create", {"name": "Skin", "color": {"r": 200, "g": 200, "b": 200}})
    await call("rhino_layer_create", {"name": "Panels::Planar", "color": {"r": 120, "g": 200, "b": 120}})
    await call("rhino_layer_create", {"name": "Panels::Curved", "color": {"r": 220, "g": 180, "b": 100}})

    # --- Build five varying-radius arc sections along Z -------------------
    section_ids = []
    profile = [(0.0, 8.0), (4.0, 9.0), (8.0, 7.5), (12.0, 6.0), (16.0, 4.5)]
    for z, radius in profile:
        arc = await call(
            "rhino_arc",
            {
                "center": {"x": 0, "y": 0, "z": z},
                "radius": radius,
                "angle_degrees": 200,  # > 180 to make a proper canopy span
                "layer": "Sections",
                "name": f"Section_z{z:04.1f}",
            },
        )
        section_ids.append(arc["summary"]["object_id"])
    print(f"Built {len(section_ids)} section arcs.")

    # --- Skin them --------------------------------------------------------
    skin = await call(
        "rhino_skin_from_sections",
        {"section_curve_ids": section_ids, "layer": "Skin", "name": "Canopy"},
    )
    skin_ids = skin["summary"]["object_ids"]
    print(f"Skin built as {len(skin_ids)} ruled segment(s).")

    # --- Per-segment panelisation + classification ------------------------
    total_classes: dict[str, int] = {}
    total_max_planarity = 0.0
    for idx, sid in enumerate(skin_ids):
        # Panelise as a quad mesh
        panels = await call(
            "rhino_uv_grid_panels",
            {
                "surface_id": sid,
                "count_u": 12,
                "count_v": 4,
                "output": "mesh",
                "layer": "Panels::Curved",
            },
        )
        # Classify each panel
        cls = await call(
            "rhino_panel_curvature_classify",
            {
                "surface_id": sid,
                "count_u": 12,
                "count_v": 4,
                "planar_tolerance": 0.005,
                "single_curve_tolerance": 0.05,
            },
        )
        seg_classes = cls["summary"]["class_counts"]
        for k, v in seg_classes.items():
            total_classes[k] = total_classes.get(k, 0) + v

        # Planarity
        plan = await call(
            "rhino_panel_planarity",
            {"surface_id": sid, "count_u": 12, "count_v": 4, "tolerance": 0.005},
        )
        seg_max = plan["summary"]["stats"]["max_error"]
        total_max_planarity = max(total_max_planarity, seg_max)
        print(
            f"  segment {idx}: panels={panels['summary']['panel_count']}, "
            f"max_planarity={seg_max:.4f} m, classes={seg_classes}"
        )

    # --- Developability summary on first segment --------------------------
    dev = await call(
        "rhino_surface_developable_score",
        {"surface_id": skin_ids[0], "sample_u": 16, "sample_v": 8},
    )
    print(
        f"Developability (segment 0): {dev['summary']['score_normalised']:.3f} "
        f"(0=developable, 1=fully doubly-curved)"
    )

    # --- Aggregate report -------------------------------------------------
    print()
    print("=" * 60)
    print("CANOPY PANEL REPORT")
    print("=" * 60)
    total_panels = sum(total_classes.values())
    for k, v in sorted(total_classes.items()):
        pct = 100.0 * v / total_panels if total_panels else 0.0
        print(f"  {k:24s}: {v:4d}  ({pct:5.1f}%)")
    print(f"  {'TOTAL panels':24s}: {total_panels:4d}")
    print(f"  {'max planarity error':24s}: {total_max_planarity:.4f} m")
    print(f"  {'developability score':24s}: {dev['summary']['score_normalised']:.3f}")
    print()

    # --- Save -------------------------------------------------------------
    await call("rhino_save", {"path": str(target), "version": 8})
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/canopy.3dm")
    sys.exit(asyncio.run(run(out)))
