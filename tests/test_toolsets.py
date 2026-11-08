"""RHINO_MCP_TOOLSETS filtering of tool registration."""

from __future__ import annotations

import logging

import pytest

from rhino_mcp.utils.registry import Mode, parse_toolsets


def _build(monkeypatch: pytest.MonkeyPatch, value: str | None) -> dict:
    from rhino_mcp.server import build_server

    if value is None:
        monkeypatch.delenv("RHINO_MCP_TOOLSETS", raising=False)
    else:
        monkeypatch.setenv("RHINO_MCP_TOOLSETS", value)
    mcp, _ = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
    return dict(mcp._tool_manager._tools)  # type: ignore[attr-defined]


@pytest.fixture
def _propagate_logs():
    parent = logging.getLogger("rhino_mcp")
    previous = parent.propagate
    parent.propagate = True
    yield
    parent.propagate = previous


def test_every_spec_has_a_known_group() -> None:
    from rhino_mcp.server import TOOLSET_GROUPS, _tool_specs

    specs = _tool_specs()
    assert all(len(spec) == 3 for spec in specs)
    assert {spec[2] for spec in specs} == set(TOOLSET_GROUPS)


def test_all_equals_default_full_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    default = _build(monkeypatch, None)
    explicit = _build(monkeypatch, "all")
    assert set(default) == set(explicit)
    assert len(default) >= 120


def test_core_drops_gh_and_keeps_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    full = _build(monkeypatch, "all")
    core = _build(monkeypatch, "core")
    assert 0 < len(core) < len(full)
    assert not [name for name in core if name.startswith("gh_")]
    assert "rhino_box" in core
    assert "rhino_execute_python" not in core
    assert "rhino_batch_call" not in core
    # bridge_admin is always registered regardless of the filter.
    admin = {name for name in full if name.startswith("rhino_bridge_")}
    assert admin, "expected bridge_admin tools in the full catalogue"
    assert admin <= set(core)


def test_groups_union_matches_full(monkeypatch: pytest.MonkeyPatch) -> None:
    full = _build(monkeypatch, "all")
    union = _build(monkeypatch, "core,bim,freeform,gh,render,scripting,docs,admin")
    assert set(union) == set(full)


def test_unknown_toolset_warns_and_is_ignored(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _propagate_logs
) -> None:
    core = _build(monkeypatch, "core")
    with caplog.at_level(logging.WARNING, logger="rhino_mcp"):
        mixed = _build(monkeypatch, " Core , bogus ")
    assert set(mixed) == set(core)
    assert any("bogus" in rec.getMessage() for rec in caplog.records)


def test_parse_toolsets() -> None:
    known = ("core", "gh")
    assert parse_toolsets(None, known) is None
    assert parse_toolsets("", known) is None
    assert parse_toolsets("all", known) is None
    assert parse_toolsets("core,all", known) is None
    assert parse_toolsets("gh, core", known) == {"gh", "core"}
    # Only unknown names: fall back to everything instead of an admin-only server.
    assert parse_toolsets("nope", known) is None


def test_viewport_navigation_is_core() -> None:
    # View set / zoom / capture are everyday modelling tools, not render-only.
    from rhino_mcp.server import CORE, _tool_specs
    from rhino_mcp.tools import display

    groups = {spec[1]: spec[2] for spec in _tool_specs()}
    assert groups[display.register] == CORE


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_documented_group_sizes_match_registration(monkeypatch: pytest.MonkeyPatch, lang: str) -> None:
    import re
    from pathlib import Path

    from rhino_mcp.server import TOOLSET_GROUPS

    doc_path = Path(__file__).resolve().parents[1] / "docs" / lang / "configuration.md"
    line = next(ln for ln in doc_path.read_text(encoding="utf-8").splitlines() if "core " in ln and "admin " in ln)
    documented = {name: int(n) for name, n in re.findall(r"\b([a-z]+) (\d+)\b", line)}
    measured = {group: len(_build(monkeypatch, group)) for group in TOOLSET_GROUPS if group != "admin"}
    admin = len(_build(monkeypatch, "admin"))
    # Every non-admin build also carries the always-on admin tools.
    actual = {group: count - admin for group, count in measured.items()} | {"admin": admin}
    assert {k: documented[k] for k in actual} == actual
