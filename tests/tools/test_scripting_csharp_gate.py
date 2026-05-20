"""Safety-gate tests for rhino_execute_csharp.

These tests do not need a live bridge — the gate fires before bridge lookup.
"""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_execute_csharp_blocked_when_env_unset(server_standalone, monkeypatch):
    monkeypatch.delenv("RHINO_MCP_ALLOW_CSHARP", raising=False)
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r"(?i)RHINO_MCP_ALLOW_CSHARP|disabled"):
        call_tool(tools, "rhino_execute_csharp", {"code": "output.AppendLine(\"hi\");"})


def test_execute_csharp_blocked_when_env_is_zero(server_standalone, monkeypatch):
    monkeypatch.setenv("RHINO_MCP_ALLOW_CSHARP", "0")
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r"(?i)RHINO_MCP_ALLOW_CSHARP|disabled"):
        call_tool(tools, "rhino_execute_csharp", {"code": "var x = 1;"})


def test_execute_csharp_passes_gate_when_enabled(server_standalone, monkeypatch):
    """When the env var is set, the gate must not be the error source.

    Whether the bridge is reachable depends on the developer's machine, so
    we only assert that the *gate-specific* error message is absent.
    """
    monkeypatch.setenv("RHINO_MCP_ALLOW_CSHARP", "1")
    _mcp, tools = server_standalone
    try:
        call_tool(tools, "rhino_execute_csharp", {"code": "var x = 1;"})
    except Exception as exc:
        assert "RHINO_MCP_ALLOW_CSHARP" not in str(exc)
        assert "disabled" not in str(exc).lower() or "C# execution is disabled" not in str(exc)
