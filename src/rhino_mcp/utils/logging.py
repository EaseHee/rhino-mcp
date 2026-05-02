"""Stderr-only logging.

Stdout is reserved for stdio-mode MCP frames; emitting to stdout corrupts the
protocol. All log output goes to stderr regardless of transport so the same
server binary works under stdio and HTTP transports.
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def configure(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    resolved = (level or os.environ.get("RHINO_MCP_LOG_LEVEL") or "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger("rhino_mcp")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, resolved, logging.INFO))
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure()
    if not name.startswith("rhino_mcp"):
        name = f"rhino_mcp.{name}"
    return logging.getLogger(name)
