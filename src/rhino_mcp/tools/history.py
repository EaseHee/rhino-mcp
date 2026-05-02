"""Undo / redo tools.

Bridge-only — operates on the live Rhino document's undo stack.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _UndoIn(BaseModel):
    steps: int = Field(1, ge=1, le=100, description="Number of operations to undo.")


class _RedoIn(BaseModel):
    steps: int = Field(1, ge=1, le=100, description="Number of operations to redo.")


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Undo"})
    def rhino_undo(args: _UndoIn) -> dict[str, Any]:
        """Undo the last operation(s) in the Rhino document.

        Each step reverses one undo record.  Changes made by MCP tools
        are grouped into undo records automatically.
        """
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_undo")

        result = runtime().require_bridge().call(
            "rhino.history.undo", {"steps": args.steps},
        )
        undone = result.get("undone_steps", 0)
        return {
            "summary": {"undone_steps": undone, "requested_steps": args.steps},
            "text": f"Undid {undone} operation(s).",
        }

    @mcp.tool(annotations={"title": "Redo"})
    def rhino_redo(args: _RedoIn) -> dict[str, Any]:
        """Redo the last undone operation(s) in the Rhino document."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_redo")

        result = runtime().require_bridge().call(
            "rhino.history.redo", {"steps": args.steps},
        )
        redone = result.get("redone_steps", 0)
        return {
            "summary": {"redone_steps": redone, "requested_steps": args.steps},
            "text": f"Redid {redone} operation(s).",
        }
