"""Tests for the modal-command circuit-breaker in tools/_safety.py.

Patterns that historically caused the bridge to disconnect (modal Rhino
commands invoked via ``rs.Command``) must be rejected before the call
reaches the bridge transport.
"""

from __future__ import annotations

import pytest

from rhino_mcp.tools._safety import check_python_payload
from rhino_mcp.utils.error_handling import ErrorCategory, ToolError

# ---------------------------------------------------------------------------
# Each entry: (payload snippet, fragment expected in the hint)
# ---------------------------------------------------------------------------

DANGEROUS_CASES = [
    ('rs.Command("_Move 0,0 1,0")', "rs.MoveObjects"),
    ('rs.Command("_Mirror 0,0 0,1")', "rs.MirrorObjects"),
    ('rs.Command("_Rotate 0,0 90")', "rs.RotateObjects"),
    ('rs.Command("_Copy 0,0 1,0")', "rs.CopyObjects"),
    ('rs.Command("_Scale 0,0 2.0")', "rs.ScaleObjects"),
    ('rs.Command("_SelLayer Default")', "rs.ObjectsByLayer"),
    ('rs.Command("_Layer _Assign Default")', "rs.ObjectLayer"),
]


@pytest.mark.parametrize("payload,hint_fragment", DANGEROUS_CASES)
def test_dangerous_pattern_is_rejected(payload: str, hint_fragment: str) -> None:
    with pytest.raises(ToolError) as exc_info:
        check_python_payload(payload)
    err = exc_info.value
    assert err.category is ErrorCategory.PARAMETER
    assert hint_fragment in err.hint


def test_first_match_wins_only_one_error() -> None:
    payload = 'rs.Command("_Move 0,0 1,0"); rs.Command("_Mirror 0,0 0,1")'
    with pytest.raises(ToolError):
        check_python_payload(payload)


def test_safe_payload_passes() -> None:
    # rs.MoveObjects is the recommended replacement and must not trip.
    check_python_payload(
        'import rhinoscriptsyntax as rs\n'
        'rs.MoveObjects(["abc", "def"], (1.0, 2.0, 0.0))'
    )


def test_command_without_modal_keyword_passes() -> None:
    # _SelAll / _SelNone are not modal in the same way; should pass.
    check_python_payload('rs.Command("_SelAll")')
    check_python_payload('rs.Command("_Save")')


def test_method_name_with_modal_substring_is_not_caught() -> None:
    # rs.MoveObjects has the substring "_Move" but is the safe API.
    check_python_payload('rs.MoveObjects(ids, (1, 0, 0))')
    check_python_payload('rs.RotateObjects(ids, origin, 45)')


def test_modal_keyword_in_docstring_or_help_passes() -> None:
    # The hardened pattern requires `rs.Command(<quote>_Verb`, so a bare
    # mention inside a string that is not the rs.Command argument should
    # not trip the check.
    check_python_payload('help_text = "Use rs.MoveObjects instead of _Move"')
    check_python_payload(
        '"""Tip: prefer rs.MoveObjects over rs.Command(legacy_move_string)."""'
    )


def test_command_with_whitespace_before_string_is_caught() -> None:
    # `rs.Command(   "_Move ...")` — extra whitespace must still be caught.
    with pytest.raises(ToolError):
        check_python_payload('rs.Command(   "_Move 0,0 1,0")')
    with pytest.raises(ToolError):
        check_python_payload("rs.Command(  '_Move 0,0 1,0')")


def test_bypass_via_environment(monkeypatch) -> None:
    monkeypatch.setenv("RHINO_MCP_ALLOW_MODAL_COMMAND", "1")
    # All dangerous patterns should pass when the bypass is set.
    for payload, _ in DANGEROUS_CASES:
        check_python_payload(payload)


def test_pattern_is_case_insensitive() -> None:
    with pytest.raises(ToolError):
        check_python_payload('rs.Command("_move 0,0 1,0")')
    with pytest.raises(ToolError):
        check_python_payload('rs.Command("_LAYER _ASSIGN Default")')
