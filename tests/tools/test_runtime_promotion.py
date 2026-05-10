"""Tests for lazy STANDALONE → BRIDGE runtime promotion.

Covers:
- Dead client cleanup in require_bridge()
- Cooldown throttle preventing back-to-back re-detections
- Successful promotion when BridgeClient.auto() returns a client
- bridge_call() resetting a dead client and triggering one re-detection
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rhino_mcp.tools import context as tool_context
from rhino_mcp.tools.context import _REDETECT_COOLDOWN, Runtime
from rhino_mcp.utils.error_handling import ErrorCategory, ToolError, connection_error
from rhino_mcp.utils.registry import Mode


def _make_alive_client() -> MagicMock:
    client = MagicMock()
    client.is_alive.return_value = True
    return client


def _make_dead_client() -> MagicMock:
    client = MagicMock()
    client.is_alive.return_value = False
    return client


class TestRequireBridge:
    def test_returns_live_client_immediately(self) -> None:
        client = _make_alive_client()
        rt = Runtime(mode=Mode.BRIDGE, bridge=client)
        assert rt.require_bridge() is client
        client.is_alive.assert_called_once()

    def test_cleans_up_dead_client_and_raises_when_no_redetect(self) -> None:
        dead = _make_dead_client()
        rt = Runtime(mode=Mode.BRIDGE, bridge=dead)
        # Set last redetect timestamp to now so cooldown blocks promotion.
        rt._last_redetect_at = time.monotonic()

        with pytest.raises(ToolError):
            rt.require_bridge()

        dead.close.assert_called_once()
        assert rt.bridge is None
        assert rt.mode is Mode.STANDALONE

    def test_promotes_to_bridge_on_first_call_from_standalone(self) -> None:
        rt = Runtime(mode=Mode.STANDALONE, bridge=None)
        promoted_client = _make_alive_client()

        with patch(
            "rhino_mcp.bridge.rhino_connection.BridgeClient.auto",
            return_value=promoted_client,
        ):
            result = rt.require_bridge()

        assert result is promoted_client
        assert rt.mode is Mode.BRIDGE
        assert rt.bridge is promoted_client

    def test_raises_when_promotion_fails(self) -> None:
        rt = Runtime(mode=Mode.STANDALONE, bridge=None)

        with patch(
            "rhino_mcp.bridge.rhino_connection.BridgeClient.auto",
            return_value=None,
        ):
            with pytest.raises(ToolError):
                rt.require_bridge()

        assert rt.bridge is None

    def test_cooldown_blocks_repeated_redetect(self) -> None:
        rt = Runtime(mode=Mode.STANDALONE, bridge=None)
        rt._last_redetect_at = time.monotonic()  # force cooldown active

        auto_calls: list[Any] = []

        def counting_auto(timeout: float = 2.0) -> None:
            auto_calls.append(timeout)
            return None

        with patch(
            "rhino_mcp.bridge.rhino_connection.BridgeClient.auto",
            side_effect=counting_auto,
        ):
            with pytest.raises(ToolError):
                rt.require_bridge()

        assert len(auto_calls) == 0, "auto() must not be called during cooldown"

    def test_redetect_after_cooldown_expires(self, monkeypatch) -> None:
        rt = Runtime(mode=Mode.STANDALONE, bridge=None)
        # Expire the cooldown by setting a past timestamp.
        rt._last_redetect_at = time.monotonic() - (_REDETECT_COOLDOWN + 1.0)
        promoted = _make_alive_client()

        with patch(
            "rhino_mcp.bridge.rhino_connection.BridgeClient.auto",
            return_value=promoted,
        ):
            result = rt.require_bridge()

        assert result is promoted


class TestBridgeCallFallback:
    """require_bridge → bridge_call connection-error reset path."""

    def test_bridge_call_resets_dead_client_and_repromotes(self) -> None:
        from rhino_mcp.tools._helpers import bridge_call

        promoted = _make_alive_client()
        promoted.call.return_value = {"summary": {}, "text": "ok"}

        dead = _make_dead_client()
        dead.is_alive.return_value = True  # alive at first require_bridge check
        dead.call.side_effect = connection_error("simulated transport failure")

        tool_context.set_runtime(Mode.BRIDGE, dead)

        with patch(
            "rhino_mcp.bridge.rhino_connection.BridgeClient.auto",
            return_value=promoted,
        ):
            result = bridge_call("rhino.test.method", {})

        assert result == {"summary": {}, "text": "ok"}
        promoted.call.assert_called_once()

    def test_bridge_call_reraises_non_connection_errors(self) -> None:
        from rhino_mcp.tools._helpers import bridge_call

        client = _make_alive_client()
        client.call.side_effect = ToolError(
            ErrorCategory.INTERNAL, "internal failure", "hint"
        )
        tool_context.set_runtime(Mode.BRIDGE, client)

        with pytest.raises(ToolError, match="internal failure"):
            bridge_call("rhino.test.method", {})
