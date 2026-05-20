"""Arbitrary script execution tools (Python / C#).

Bridge-only — requires a live Rhino session.  These are the "escape hatch"
tools that allow callers to run full RhinoScript Python or RhinoCommon C#
code when the built-in primitive tools are insufficient.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools._safety import check_python_payload
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode

log = get_logger("scripting")

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
    references: list[str] | None = Field(
        None,
        max_length=32,
        description=(
            "Additional assembly names (e.g. ``Grasshopper`` or "
            "``System.Xml.Linq``) to load before compilation. Each is "
            "resolved with ``Assembly.Load(name)``."
        ),
    )
    timeout_s: int = Field(
        30,
        ge=1,
        le=600,
        description="Maximum seconds to wait for the script to complete.",
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

    @mcp.tool(annotations={"title": "Execute RhinoCommon C# Code", "destructiveHint": True})
    def rhino_execute_csharp(args: _ExecCSharpIn) -> dict[str, Any]:
        """Execute RhinoCommon C# code in a live Rhino session using Roslyn.

        SAFETY: This tool runs arbitrary code with full RhinoCommon access.
        It is gated behind ``RHINO_MCP_ALLOW_CSHARP=1`` so it cannot fire
        accidentally. Set the env var only in trusted sessions.

        Globals available to the script:
        - ``doc``: the active ``RhinoDoc``
        - ``output``: a ``StringBuilder`` — call ``output.AppendLine("...")``
          to return text to the caller.

        Pre-imported namespaces: System, System.Collections.Generic,
        System.Linq, System.Text, Rhino, Rhino.Geometry, Rhino.DocObjects,
        Rhino.Commands. Pass ``references`` to load extra assemblies (e.g.
        ``Grasshopper``).

        Example — create a sphere::

            var sphere = new Sphere(Point3d.Origin, 5.0);
            doc.Objects.AddBrep(sphere.ToBrep());
            doc.Views.Redraw();
            output.AppendLine("Created sphere");

        Changes are wrapped in an undo record. ``timeout_s`` caps total
        execution time (default 30s); on timeout the call returns
        ``success: false`` and the script is best-effort cancelled.
        """
        if os.environ.get("RHINO_MCP_ALLOW_CSHARP", "0") != "1":
            raise parameter_error(
                "RHINO_MCP_ALLOW_CSHARP",
                "C# execution is disabled. Set RHINO_MCP_ALLOW_CSHARP=1 in the "
                "Rhino process environment to enable this tool. Audit the "
                "request first — Roslyn scripts have full RhinoCommon access.",
            )
        # Audit trail: the request id propagates from the MCP transport; the
        # bridge writes its own RhinoApp.WriteLine. Echo a one-liner so the
        # server-side log captures the intent too.
        log.warning(
            "rhino_execute_csharp invoked (code_len=%d, refs=%d, timeout=%ds)",
            len(args.code),
            len(args.references or []),
            args.timeout_s,
        )
        result = runtime().require_bridge().call(
            "rhino.script.execute_csharp",
            {
                "code": args.code,
                "references": args.references or [],
                "timeout_s": args.timeout_s,
            },
        )
        return {
            "summary": {
                "success": result.get("success", True),
                "output": result.get("output", ""),
                "timed_out": result.get("timed_out", False),
            },
            "text": result.get("result", result.get("message", "Script executed.")),
        }
