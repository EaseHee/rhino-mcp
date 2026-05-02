"""rhino-mcp server entrypoint.

Boots a FastMCP server and registers every tool module whose declared
capability matches the detected runtime mode (BRIDGE or STANDALONE). The CLI
exposes minimal flags; everything else flows through environment variables so
the same binary works under Claude Desktop's stdio transport, a Streamable HTTP
deployment, and the Docker compose file.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from rhino_mcp import __version__
from rhino_mcp.bridge.rhino_connection import BridgeClient, detect_mode
from rhino_mcp.transport import fastmcp_transport_arg, resolve_transport
from rhino_mcp.utils.logging import configure as configure_logging
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode, register_tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

log = get_logger("server")


def _tool_specs() -> list[tuple[Mode, object]]:
    """Lazy-import every tool module's ``register`` along with its capability mode."""
    from rhino_mcp.tools import (
        analysis,
        annotation,
        batch,
        composition,
        control_points,
        curves,
        deformation,
        display,
        document_config,
        extraction,
        geometry,
        geometry_validation,
        history,
        io,
        layers,
        materials,
        mesh,
        nurbs,
        paneling,
        query,
        rhinoscript_docs,
        scripting,
        solids,
        subd,
        surface_match,
        surfaces,
        transform,
    )
    from rhino_mcp.tools.freeform import curvature as ff_curvature
    from rhino_mcp.tools.freeform import fields as ff_fields
    from rhino_mcp.tools.freeform import paneling as ff_paneling
    from rhino_mcp.tools.freeform import skin as ff_skin
    from rhino_mcp.tools.grasshopper import canvas, components, data_tree, parameters, templates

    return [
        # Core geometry (standalone + bridge)
        (Mode.BOTH, geometry.register),
        (Mode.BOTH, curves.register),
        (Mode.BOTH, solids.register),
        (Mode.BOTH, surfaces.register),
        (Mode.BOTH, mesh.register),
        (Mode.BOTH, transform.register),
        (Mode.BOTH, composition.register),
        (Mode.BOTH, annotation.register),
        (Mode.BOTH, layers.register),
        (Mode.BOTH, materials.register),
        (Mode.BOTH, io.register),
        (Mode.BOTH, analysis.register),
        (Mode.BOTH, query.register),
        (Mode.BOTH, document_config.register),
        (Mode.BOTH, geometry_validation.register),
        # Freeform / non-rectilinear architecture (v0.3)
        (Mode.BOTH, ff_skin.register),
        (Mode.BOTH, ff_paneling.register),
        (Mode.BOTH, ff_curvature.register),
        (Mode.BOTH, ff_fields.register),
        # Documentation (standalone + bridge)
        (Mode.BOTH, rhinoscript_docs.register),
        # Script execution (bridge only)
        (Mode.BRIDGE, scripting.register),
        # History (bridge only)
        (Mode.BRIDGE, history.register),
        # Batch operations (bridge only)
        (Mode.BRIDGE, batch.register),
        # Advanced modeling (bridge only)
        (Mode.BRIDGE, deformation.register),
        (Mode.BRIDGE, nurbs.register),
        (Mode.BRIDGE, subd.register),
        (Mode.BRIDGE, surface_match.register),
        (Mode.BRIDGE, extraction.register),
        (Mode.BRIDGE, control_points.register),
        (Mode.BRIDGE, paneling.register),
        # Display & Grasshopper (bridge only)
        (Mode.BRIDGE, display.register),
        (Mode.BRIDGE, components.register),
        (Mode.BRIDGE, parameters.register),
        (Mode.BRIDGE, canvas.register),
        (Mode.BRIDGE, data_tree.register),
        (Mode.BOTH, templates.register),
    ]


def build_server(
    runtime_mode: Mode | None = None,
    bridge_client: BridgeClient | None = None,
) -> tuple[FastMCP, int]:
    """Construct and configure the FastMCP server. Returns ``(mcp, tool_count)``."""
    from mcp.server.fastmcp import FastMCP

    if runtime_mode is None:
        runtime_mode, bridge_client = detect_mode()

    from rhino_mcp.tools.context import set_runtime

    set_runtime(runtime_mode, bridge_client)

    mcp = FastMCP(
        "rhino-mcp",
        instructions=(
            "Drive McNeel Rhino 8 and Grasshopper through MCP. "
            "Each tool returns structured JSON (object IDs, bounding boxes, etc.) "
            "and a short human-readable summary. Standalone mode uses rhino3dm "
            "for headless 3DM I/O; bridge mode forwards calls to a live Rhino 8 "
            "session running RhinoMCPBridge."
        ),
    )

    applied = register_tools(mcp, runtime_mode, _tool_specs())
    prompts = _register_prompts(mcp)
    log.info(
        "Registered %d tool modules and %d prompts (mode=%s)",
        applied,
        prompts,
        runtime_mode.value,
    )
    return mcp, applied


def _register_prompts(mcp: FastMCP) -> int:
    """Register MCP prompts (strategic guidance for LLM tool selection)."""
    from rhino_mcp.prompts import strategy

    funcs = (
        strategy.general_strategy,
        strategy.rhinoscript_workflow,
        strategy.viewport_workflow,
        strategy.parametric_workflow,
        strategy.bim_authoring_workflow,
        strategy.design_dialogue_workflow,
        strategy.freeform_workflow,
    )
    for fn in funcs:
        mcp.prompt(name=fn.__name__, description=(fn.__doc__ or "").strip())(fn)
    return len(funcs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rhino-mcp",
        description="MCP server for Rhino 8 and Grasshopper.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=None,
        help="MCP transport (default: stdio; env RHINO_MCP_TRANSPORT overrides).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host for HTTP transport (default 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for HTTP transport (default 8765).",
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help=(
            "Disable DNS-rebinding protection so external clients (e.g. claude.ai connector, "
            "ngrok) can reach the HTTP server. Use with --transport http only."
        ),
    )
    parser.add_argument(
        "--stateless",
        action="store_true",
        help=(
            "Enable stateless HTTP mode (no session state between requests). "
            "Required for claude.ai remote connectors."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"rhino-mcp {__version__}",
    )
    args = parser.parse_args(argv)

    configure_logging()
    transport_kind = resolve_transport(args.transport)

    try:
        mcp, _ = build_server()
    except ImportError as exc:
        log.error("Missing dependency: %s", exc)
        print(f"Error: required package not found — {exc}", file=sys.stderr)
        return 2
    except ConnectionError as exc:
        log.error("Bridge connection failed: %s", exc)
        print(f"Error: bridge connection failed — {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        log.error("Server initialization failed: %s", exc)
        print(f"Error: server startup failed — {exc}", file=sys.stderr)
        return 1

    fastmcp_kind = fastmcp_transport_arg(transport_kind)
    if fastmcp_kind == "streamable-http":
        # Apply host/port overrides.
        if args.host is not None:
            mcp.settings.host = args.host
        if args.port is not None:
            mcp.settings.port = args.port

        # Connector mode: allow external hosts and enable stateless requests.
        if args.allow_external:
            ts = mcp.settings.transport_security
            ts.enable_dns_rebinding_protection = False
            ts.allowed_hosts = ["*"]
            ts.allowed_origins = ["*"]
            log.info("External access enabled (DNS-rebinding protection disabled)")
        if args.stateless:
            mcp.settings.stateless_http = True
            log.info("Stateless HTTP mode enabled")

        host = mcp.settings.host
        port = mcp.settings.port
        log.info("Starting Streamable HTTP transport on %s:%s/mcp", host, port)
        if args.allow_external:
            log.info(
                "MCP endpoint: http://%s:%s/mcp  "
                "(expose via ngrok/cloudflare for claude.ai connector)",
                host,
                port,
            )
    else:
        log.info("Starting stdio transport")

    try:
        mcp.run(transport=fastmcp_kind)
    except KeyboardInterrupt:
        log.info("Shutting down (interrupted).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
