"""Shared pytest fixtures."""

from __future__ import annotations

import os
from typing import Any

import pytest

# Force standalone mode in tests so the server never tries to dial out.
os.environ.setdefault("RHINO_MCP_FORCE_MODE", "standalone")

from rhino_mcp.document import registry as _doc_registry
from rhino_mcp.tools import context as tool_context
from rhino_mcp.utils.registry import Mode

# Enable test mode so runtime() falls back to STANDALONE when _RUNTIME is unset.
tool_context.enable_testing()


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test starts with a fresh document registry and standalone runtime."""
    _doc_registry().reset()
    tool_context.set_runtime(Mode.STANDALONE, None)
    yield
    _doc_registry().reset()
    tool_context.reset()


@pytest.fixture
def fresh_doc():
    """Yield a fresh standalone document."""
    handle = _doc_registry().get_or_create("test")
    yield handle


def _get_tools(mcp):
    """Extract FastMCP's internal tool dict (test helper)."""
    mgr = getattr(mcp, "_tool_manager", None)
    if mgr is not None:
        return mgr._tools  # type: ignore[attr-defined]
    return {}


@pytest.fixture
def server_standalone():
    """Build the FastMCP server in standalone mode and return ``(mcp, tools_dict)``."""
    from rhino_mcp.server import build_server

    mcp, _count = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
    return mcp, _get_tools(mcp)


@pytest.fixture
def server_bridge():
    """Build the FastMCP server in bridge mode (without a real client)."""
    from rhino_mcp.server import build_server

    mcp, _count = build_server(runtime_mode=Mode.BRIDGE, bridge_client=None)
    return mcp, _get_tools(mcp)


def call_tool(tools: dict[str, Any], name: str, payload: dict[str, Any]) -> Any:
    """Invoke a registered tool by name through the FastMCP wrapper.

    All our tool functions take a single pydantic model named ``args``; FastMCP
    wraps that into ``{"args": {...}}`` at the call boundary.
    """
    import asyncio

    tool = tools[name]
    coro = tool.run({"args": payload})
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Reuse the running loop in async tests.
    return loop.run_until_complete(coro)
