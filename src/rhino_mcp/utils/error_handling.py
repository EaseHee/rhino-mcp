"""Structured tool errors.

Each error pairs a category with an actionable hint so the client surfaces
something the user can act on, not just "operation failed".
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    PARAMETER = "parameter"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"
    GH_COMPONENT = "gh_component"
    INTERNAL = "internal"


class ToolError(Exception):
    """Base class for tool-level failures.

    Args:
        category: high-level reason; clients can branch on this.
        message: short human-readable summary (one line).
        hint: concrete remediation step.
        details: optional structured payload (parameter name, allowed range, etc.).
    """

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        hint: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.hint = hint
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "category": self.category.value,
                "message": self.message,
                "hint": self.hint,
                "details": self.details,
            }
        }


def connection_error(detail: str = "") -> ToolError:
    return ToolError(
        ErrorCategory.CONNECTION,
        "Cannot reach Rhino bridge.",
        (
            "Start Rhino 8 with the rhino-mcp.rhp C# plugin loaded "
            "(dotnet build rhino_plugin/csharp -c Release, then drag-drop the .rhp), "
            "and verify the transport (named pipe on Windows, unix socket on macOS/Linux, "
            "or TCP on $RHINO_HOST:$RHINO_PORT). "
            + (detail if detail else "")
        ).strip(),
    )


def parameter_error(name: str, message: str, allowed: str | None = None) -> ToolError:
    hint = f"Parameter '{name}': {message}."
    if allowed:
        hint += f" Allowed: {allowed}."
    return ToolError(
        ErrorCategory.PARAMETER,
        f"Invalid parameter: {name}",
        hint,
        details={"parameter": name, "allowed": allowed},
    )


def not_found_error(what: str, identifier: str) -> ToolError:
    return ToolError(
        ErrorCategory.NOT_FOUND,
        f"{what} not found: {identifier}",
        "Pass an absolute path or a valid identifier. Use `rhino_open` (or `gh_open_file`) "
        "first if the document/component must be loaded.",
        details={"what": what, "identifier": identifier},
    )


def unsupported_in_standalone(tool: str) -> ToolError:
    return ToolError(
        ErrorCategory.UNSUPPORTED,
        f"Tool '{tool}' requires Rhino bridge mode.",
        "Start Rhino 8 with the rhino-mcp.rhp C# plugin loaded and re-run; rhino3dm standalone cannot perform this operation.",
        details={"tool": tool, "reason": "rhino3dm lacks the underlying API"},
    )


def gh_component_missing(component_name: str, suggestion: str | None = None) -> ToolError:
    return ToolError(
        ErrorCategory.GH_COMPONENT,
        f"Grasshopper component not found: {component_name}",
        (
            f"Install the plug-in that provides '{component_name}', or use "
            + (f"'{suggestion}' instead." if suggestion else "an alternative component.")
        ),
        details={"component": component_name, "suggestion": suggestion},
    )
