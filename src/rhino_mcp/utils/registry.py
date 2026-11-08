"""Capability matrix and conditional tool registration.

Each tool declares which execution mode it supports:

* ``Mode.STANDALONE`` — runs against an in-process ``rhino3dm.File3dm``.
* ``Mode.BRIDGE`` — proxies through the ``rhino-mcp.rhp`` C# plugin loaded inside a live Rhino 8 or 9.
* ``Mode.BOTH`` — supported in both, with implementation chosen at runtime.

Tools whose capability does not match the active mode are simply not registered
on the MCP server. The spec forbids stub functions; this is how we honour it
while still claiming the full tool catalogue when the bridge is present.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Collection, Iterable
from enum import StrEnum
from typing import Any

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


TOOLSETS_ENV = "RHINO_MCP_TOOLSETS"
ALL_TOOLSETS = "all"

ToolSpec = tuple[Mode, Callable[..., None]] | tuple[Mode, Callable[..., None], str]


def parse_toolsets(raw: str | None, known: Collection[str]) -> set[str] | None:
    """Parse a comma-separated toolset list.

    Returns ``None`` when every group should be registered (empty input, an
    ``all`` entry, or no known name at all). Unknown names are logged at
    WARNING and dropped.
    """
    if raw is None:
        return None
    names = [part.strip().lower() for part in raw.split(",") if part.strip()]
    if not names or ALL_TOOLSETS in names:
        return None
    known_set = set(known)
    selected: set[str] = set()
    for name in names:
        if name in known_set:
            selected.add(name)
        else:
            log.warning(
                "Unknown toolset %r in %s ignored (known: %s)",
                name,
                TOOLSETS_ENV,
                ", ".join(sorted(known_set)),
            )
    if not selected:
        # A list of pure typos should not silently strip the server down to admin tools.
        log.warning("No known toolset in %s=%r; registering all toolsets", TOOLSETS_ENV, raw)
        return None
    return selected


def toolsets_from_env(known: Collection[str]) -> set[str] | None:
    """Read ``RHINO_MCP_TOOLSETS`` (default ``all``) and parse it."""
    return parse_toolsets(os.environ.get(TOOLSETS_ENV, ALL_TOOLSETS), known)


def _tool_count(mcp: Any) -> int | None:
    """Return the number of tools registered on a FastMCP instance, if observable."""
    manager = getattr(mcp, "_tool_manager", None)
    if manager is None:
        return None
    try:
        return len(manager.list_tools())
    except Exception:
        return None


def register_tools(
    mcp: Any,  # FastMCP instance; typed loosely to keep the import optional in tests
    runtime_mode: Mode,
    specs: Iterable[ToolSpec],
    *,
    toolsets: Collection[str] | None = None,
    always_groups: Collection[str] = (),
) -> int:
    """Apply each ``register_fn(mcp, mode)`` whose declared capability matches ``runtime_mode``.

    Each register function receives ``(mcp, mode)`` so it can gate individual
    tools (e.g. a module that has both standalone-OK and bridge-only tools can
    register the standalone subset in standalone mode and the full set in bridge mode).

    A spec may carry a third element naming its toolset group. When
    ``toolsets`` is given, only specs whose group is in it (or in
    ``always_groups``) are applied; ``None`` applies every group. Specs
    without a group are treated as always-on.

    Returns the number of register-functions actually applied.
    """
    applied = 0
    per_group: dict[str, int] = {}
    for spec in specs:
        capability, register_fn = spec[0], spec[1]
        group = spec[2] if len(spec) > 2 else None
        if (
            toolsets is not None
            and group is not None
            and group not in toolsets
            and group not in always_groups
        ):
            continue
        if not is_compatible(capability, runtime_mode):
            continue
        before = _tool_count(mcp)
        register_fn(mcp, runtime_mode)
        applied += 1
        after = _tool_count(mcp)
        if group is not None and before is not None and after is not None:
            per_group[group] = per_group.get(group, 0) + (after - before)
    if applied == 0:
        log.warning(
            "No tool modules matched mode=%s. Check _tool_specs() configuration.",
            runtime_mode.value,
        )
    for group in sorted(per_group):
        log.info("Toolset %s: %d tools registered", group, per_group[group])
    return applied
