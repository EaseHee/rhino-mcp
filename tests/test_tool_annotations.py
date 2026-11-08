"""Tool annotations must match what the tool name promises.

MCP clients use ``readOnlyHint`` to auto-approve calls and
``destructiveHint`` to warn before them, so a query tool marked writable
costs the user a prompt and a delete tool marked safe skips a warning.
"""

from __future__ import annotations

import re

import pytest

# Suffix verbs that only read the document. Viewport captures are excluded:
# they can write a file at a caller-chosen path.
_READ_ONLY = re.compile(
    r"_(get|list|info|count|search|find|query|summary|describe|inspect|details|status|"
    r"check|validate|analy[sz]e|measure|area|volume|length|bounding_box|distance)(_|$)"
)
_DESTRUCTIVE = re.compile(r"_(delete|remove|purge|clear|reset)(_|$)")

# Names that match a read-only verb but change state.
_READ_ONLY_EXCEPTIONS = {
    "gh_preview_toggle",  # toggles component preview on the canvas
}


def _annotations(tools: dict, name: str):  # type: ignore[no-untyped-def]
    return tools[name].annotations


@pytest.fixture
def tools(server_standalone):  # type: ignore[no-untyped-def]
    _mcp, registered = server_standalone
    return registered


def test_patterns_select_known_tools(tools) -> None:  # type: ignore[no-untyped-def]
    # Guard against the regexes silently matching nothing.
    read_names = {n for n in tools if _READ_ONLY.search(n)}
    destructive_names = {n for n in tools if _DESTRUCTIVE.search(n)}
    assert {"rhino_layer_list", "rhino_subd_inspect"} <= read_names
    assert {"rhino_object_delete", "rhino_layer_delete"} <= destructive_names


def test_read_tools_are_read_only(tools) -> None:  # type: ignore[no-untyped-def]
    offenders = sorted(
        name
        for name in tools
        if _READ_ONLY.search(name)
        and name not in _READ_ONLY_EXCEPTIONS
        and not getattr(_annotations(tools, name), "readOnlyHint", False)
    )
    assert offenders == []


def test_delete_tools_are_destructive(tools) -> None:  # type: ignore[no-untyped-def]
    offenders = sorted(
        name
        for name in tools
        if _DESTRUCTIVE.search(name)
        and not getattr(_annotations(tools, name), "destructiveHint", False)
    )
    assert offenders == []


def test_read_only_tools_are_not_destructive(tools) -> None:  # type: ignore[no-untyped-def]
    offenders = sorted(
        name
        for name, tool in tools.items()
        if getattr(tool.annotations, "readOnlyHint", False)
        and getattr(tool.annotations, "destructiveHint", False)
    )
    assert offenders == []
