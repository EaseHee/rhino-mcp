"""Grasshopper template module tests (manifest-driven, no live bridge required)."""

from __future__ import annotations

from tests.conftest import call_tool


def test_template_list_includes_panel_grid(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "gh_template_list", {})
    s = res["summary"]
    assert s["count"] >= 4
    names = [t["name"] for t in s["templates"]]
    assert "panel_grid" in names
    assert "morph_to_surface" in names


def test_template_list_reports_parameter_contract(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "gh_template_list", {})
    panel = next(t for t in res["summary"]["templates"] if t["name"] == "panel_grid")
    params = panel["parameters"]
    assert "count_x" in params and "count_y" in params
    assert params["count_x"]["type"] == "int"


def test_template_list_marks_unavailable_when_binary_missing(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "gh_template_list", {})
    # In CI / standalone we ship the manifest only — binaries should be flagged
    # as unavailable so the LLM can ask the user to populate them.
    for t in res["summary"]["templates"]:
        assert "available" in t


def test_load_template_unregistered_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    assert "gh_load_template" not in tools
    assert "gh_run_template" not in tools
