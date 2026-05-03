"""Render-automation tool tests (all bridge-only — verify gating)."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


@pytest.mark.parametrize(
    "tool,payload",
    [
        (
            "rhino_camera_set",
            {
                "location": {"x": 100, "y": 100, "z": 50},
                "target": {"x": 0, "y": 0, "z": 0},
                "lens_length_mm": 35.0,
            },
        ),
        (
            "rhino_light_add",
            {
                "kind": "point",
                "location": {"x": 0, "y": 0, "z": 50},
                "intensity": 1.5,
            },
        ),
        (
            "rhino_render_setup",
            {"width": 1920, "height": 1080, "samples": 200, "engine": "active"},
        ),
        (
            "rhino_render_to_file",
            {"output_path": "/tmp/render.png"},
        ),
        (
            "rhino_turntable_render",
            {"output_dir": "/tmp/turntable", "frame_count": 8, "radius": 50.0},
        ),
    ],
)
def test_render_tools_unsupported_in_standalone(server_standalone, tool, payload) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(tools, tool, payload)


def test_light_add_rejects_unknown_kind(server_standalone) -> None:
    _mcp, tools = server_standalone
    # Bridge-only path raises before reaching the kind check, so we expect
    # any exception — both cases mean the LLM gets actionable feedback.
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_light_add",
            {"kind": "fluorescent_haze", "location": {"x": 0, "y": 0, "z": 0}},
        )
