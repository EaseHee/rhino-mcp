"""Arbitrary script execution tools (Python / C#).

Bridge-only — requires a live Rhino session.  These are the "escape hatch"
tools that allow callers to run full RhinoScript Python or RhinoCommon C#
code when the built-in primitive tools are insufficient.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools._safety import check_python_payload
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode

# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


class _ExecPythonIn(BaseModel):
    code: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="RhinoScript Python code to execute in Rhino.",
    )
    verified_functions: list[str] | None = Field(
        None,
        description=(
            "List of function names you verified via "
            "rhino_get_rhinoscript_docs before writing the code."
        ),
    )


class _ExecCSharpIn(BaseModel):
    code: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="RhinoCommon C# code to execute in Rhino.",
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: Any, mode: Mode) -> None:
    @mcp.tool(annotations={"title": "Execute RhinoScript Python Code"})
    def rhino_execute_python(args: _ExecPythonIn) -> dict[str, Any]:
        """Execute RhinoScript Python code in a live Rhino session.

        CRITICAL — BEFORE USING THIS TOOL:
        1. Call rhino_get_rhinoscript_docs(topic) to find correct signatures.
        2. Read the documentation carefully — note exact parameter types.
        3. Write code using ONLY the documented signatures.
        4. Call this tool with the code.

        Code requirements:
        - Import rhinoscriptsyntax: ``import rhinoscriptsyntax as rs``
        - Use ``print()`` to return output/results to the caller.
        - Handle ``None`` returns from functions that might fail.

        Changes are wrapped in an undo record and will be reverted on failure.

        Returns ``success``, ``output`` (print capture), and ``message``
        (error details on failure).
        """
        # Safety check first — reject bridge-hostile rs.Command patterns
        # before paying the bridge round-trip cost.
        check_python_payload(args.code)

        # require_bridge() handles lazy STANDALONE -> BRIDGE promotion and
        # raises connection_error when no bridge is reachable.
        result = runtime().require_bridge().call(
            "rhino.script.execute_python",
            {"code": args.code},
        )
        return {
            "summary": {
                "success": result.get("success", True),
                "output": result.get("output", result.get("result", "")),
            },
            "text": result.get("result", "Script executed."),
        }

    @mcp.tool(annotations={"title": "Execute RhinoCommon C# Code"})
    def rhino_execute_csharp(args: _ExecCSharpIn) -> dict[str, Any]:
        """Execute RhinoCommon C# code in a live Rhino session using Roslyn.

        The code runs with these globals pre-injected:
        - ``doc``: The active ``RhinoDoc`` (Rhino.RhinoDoc)
        - ``output``: A ``StringBuilder`` — call ``output.AppendLine("...")``
          to return results.

        Common namespaces are pre-imported:
        System, System.Collections.Generic, System.Linq,
        Rhino, Rhino.Geometry, Rhino.DocObjects, Rhino.Commands.

        Example — create a sphere::

            var sphere = new Sphere(Point3d.Origin, 5.0);
            doc.Objects.AddBrep(sphere.ToBrep());
            doc.Views.Redraw();
            output.AppendLine("Created sphere");

        Changes are wrapped in an undo record and will be reverted on failure.
        Compilation errors are returned in ``message``.
        """
        result = runtime().require_bridge().call(
            "rhino.script.execute_csharp",
            {"code": args.code},
        )
        return {
            "summary": {
                "success": result.get("success", True),
                "output": result.get("output", ""),
            },
            "text": result.get("result", result.get("message", "Script executed.")),
        }
