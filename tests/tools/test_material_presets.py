"""Material preset tests (catalogue + creation + bridge gating)."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_preset_list_has_entries(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "rhino_material_preset_list", {})
    assert res["summary"]["count"] > 10
    names = [r["name"] for r in res["summary"]["presets"]]
    assert "concrete_cip" in names
    assert "glass_clear" in names


def test_preset_list_filtered_by_category(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "rhino_material_preset_list", {"category": "metal"})
    cats = {r["category"] for r in res["summary"]["presets"]}
    assert cats == {"metal"}


def test_preset_create_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_material_preset_create",
        {"preset_name": "concrete_cip"},
    )
    assert res["summary"]["preset"] == "concrete_cip"
    assert res["summary"]["category"] == "stone"
    assert res["summary"]["index"] >= 0


def test_preset_create_unknown_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_material_preset_create",
            {"preset_name": "imaginary_preset_xyz"},
        )


def test_environment_set_unsupported_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_environment_set",
            {"hdri_path": "/tmp/sky.exr", "rotation_deg": 0.0},
        )
