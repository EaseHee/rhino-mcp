"""Capability matrix and conditional tool registration.

Each tool declares which execution mode it supports:

* ``Mode.STANDALONE`` — runs against an in-process ``rhino3dm.File3dm``.
* ``Mode.BRIDGE`` — proxies through the ``RhinoMCPBridge.rhp`` C# plugin loaded inside a live Rhino 8.
* ``Mode.BOTH`` — supported in both, with implementation chosen at runtime.

Tools whose capability does not match the active mode are simply not registered
on the MCP server. The spec forbids stub functions; this is how we honour it
while still claiming the full tool catalogue when the bridge is present.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from enum import StrEnum

log = logging.getLogger("rhino_mcp.registry")


class Mode(StrEnum):
    STANDALONE = "standalone"
    BRIDGE = "bridge"
    BOTH = "both"


def is_compatible(tool_capability: Mode, runtime_mode: Mode) -> bool:
    """Return True if a tool with ``tool_capability`` should run under ``runtime_mode``."""
    if tool_capability is Mode.BOTH:
        return True
    if runtime_mode is Mode.BRIDGE:
        return tool_capability in (Mode.BRIDGE, Mode.BOTH)
    if runtime_mode is Mode.STANDALONE:
        return tool_capability in (Mode.STANDALONE, Mode.BOTH)
    return False


def register_tools(
    mcp,  # FastMCP instance; not annotated to keep the import optional in tests
    runtime_mode: Mode,
    specs: Iterable[tuple[Mode, Callable[..., None]]],
) -> int:
    """Apply each ``register_fn(mcp, mode)`` whose declared capability matches ``runtime_mode``.

    Each register function receives ``(mcp, mode)`` so it can gate individual
    tools (e.g. a module that has both standalone-OK and bridge-only tools can
    register the standalone subset in standalone mode and the full set in bridge mode).

    Returns the number of register-functions actually applied.
    """
    applied = 0
    for capability, register_fn in specs:
        if is_compatible(capability, runtime_mode):
            register_fn(mcp, runtime_mode)
            applied += 1
    if applied == 0:
        log.warning(
            "No tool modules matched mode=%s. Check _tool_specs() configuration.",
            runtime_mode.value,
        )
    return applied
