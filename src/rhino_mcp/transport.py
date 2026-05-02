"""MCP-side transport selection (stdio vs Streamable HTTP)."""

from __future__ import annotations

import os
from typing import Literal

TransportKind = Literal["stdio", "http"]


def resolve_transport(cli_value: str | None = None) -> TransportKind:
    """Pick the MCP transport kind from CLI or env.

    Priority: explicit CLI flag > ``RHINO_MCP_TRANSPORT`` env > ``stdio``.
    """
    explicit = (cli_value or os.environ.get("RHINO_MCP_TRANSPORT") or "stdio").lower()
    if explicit not in ("stdio", "http", "streamable-http"):
        raise ValueError(
            f"Unknown transport '{explicit}'. Use 'stdio' or 'http'."
        )
    return "http" if explicit in ("http", "streamable-http") else "stdio"


def fastmcp_transport_arg(kind: TransportKind) -> str:
    """Translate to the string FastMCP's ``run`` accepts."""
    return "streamable-http" if kind == "http" else "stdio"
