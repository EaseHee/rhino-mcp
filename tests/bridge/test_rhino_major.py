"""Rhino major-version mismatch warning on bridge connect."""

from __future__ import annotations

from typing import Any

import pytest

from rhino_mcp.bridge import rhino_connection
from rhino_mcp.bridge.rhino_connection import _check_protocol


def _pong(running: object, built_for: object) -> dict[str, object]:
    return {"protocol_version": "9.9", "rhino_major": running, "plugin_built_for": built_for}


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []

    def fake_warning(msg: str, *args: Any) -> None:
        captured.append(msg % args)

    # The package logger does not propagate, so caplog cannot see it.
    monkeypatch.setattr(rhino_connection.log, "warning", fake_warning)
    return captured


def test_mismatch_warns(warnings: list[str]) -> None:
    _check_protocol(_pong(9, 8), "tcp")
    assert len(warnings) == 1
    assert "runs in Rhino 9 but the plug-in was built for Rhino 8" in warnings[0]
    assert "rh9" in warnings[0]


@pytest.mark.parametrize(
    ("running", "built_for"),
    [(9, 9), (8, 8), (None, 8), ("9", 8)],
)
def test_no_warning_when_matching_or_unknown(
    warnings: list[str], running: object, built_for: object
) -> None:
    _check_protocol(_pong(running, built_for), "tcp")
    assert warnings == []
