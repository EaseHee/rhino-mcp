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
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from rhino_mcp import __version__
from rhino_mcp.bridge.rhino_connection import BridgeClient, detect_mode
from rhino_mcp.transport import fastmcp_transport_arg, resolve_transport
from rhino_mcp.utils.logging import configure as configure_logging
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode, register_tools, toolsets_from_env

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

log = get_logger("server")


# Toolset groups selectable through RHINO_MCP_TOOLSETS.
CORE = "core"
BIM = "bim"
FREEFORM = "freeform"
GH = "gh"
RENDER = "render"
SCRIPTING = "scripting"
DOCS = "docs"
ADMIN = "admin"

TOOLSET_GROUPS: tuple[str, ...] = (CORE, BIM, FREEFORM, GH, RENDER, SCRIPTING, DOCS, ADMIN)
# Groups registered regardless of the toolset filter.
ALWAYS_ON_GROUPS: frozenset[str] = frozenset({ADMIN})


def _tool_specs() -> list[tuple[Mode, Callable[..., None], str]]:
    """Lazy-import every tool module's ``register`` with its capability mode and toolset group."""
    from rhino_mcp.tools import (
        analysis,
        annotation,
        batch,
        batch_call,
        bim_io,
        blocks,
        bridge_admin,
        composition,
        control_points,
        curves,
        deformation,
        display,
        document_config,
        drawing,
        environment,
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
        render,
        rhinoscript_docs,
        schedule,
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
        (Mode.BOTH, geometry.register, CORE),
        (Mode.BOTH, curves.register, CORE),
        (Mode.BOTH, solids.register, CORE),
        (Mode.BOTH, surfaces.register, CORE),
        (Mode.BOTH, mesh.register, CORE),
        (Mode.BOTH, transform.register, CORE),
        (Mode.BOTH, composition.register, CORE),
        (Mode.BOTH, annotation.register, CORE),
        (Mode.BOTH, layers.register, CORE),
        (Mode.BOTH, materials.register, CORE),
        (Mode.BOTH, io.register, CORE),
        (Mode.BOTH, analysis.register, CORE),
        (Mode.BOTH, query.register, CORE),
        (Mode.BOTH, document_config.register, CORE),
        (Mode.BOTH, geometry_validation.register, CORE),
        # Drawing / quantity / blocks / environment (v0.3)
        (Mode.BOTH, drawing.register, BIM),
        (Mode.BOTH, schedule.register, BIM),
        (Mode.BOTH, blocks.register, CORE),
        (Mode.BOTH, environment.register, BIM),
        # BIM interchange / render automation (v0.3)
        (Mode.BOTH, bim_io.register, BIM),
        (Mode.BRIDGE, render.register, RENDER),
        # Freeform / non-rectilinear architecture (v0.3)
        (Mode.BOTH, ff_skin.register, FREEFORM),
        (Mode.BOTH, ff_paneling.register, FREEFORM),
        (Mode.BOTH, ff_curvature.register, FREEFORM),
        (Mode.BOTH, ff_fields.register, FREEFORM),
        # Documentation (standalone + bridge)
        (Mode.BOTH, rhinoscript_docs.register, DOCS),
        # Bridge administration: multi-Rhino discovery and endpoint switch
        (Mode.BOTH, bridge_admin.register, ADMIN),
        # Script execution (bridge only)
        (Mode.BRIDGE, scripting.register, SCRIPTING),
        # History (bridge only)
        (Mode.BRIDGE, history.register, CORE),
        # Batch operations (bridge only)
        (Mode.BRIDGE, batch.register, SCRIPTING),
        (Mode.BRIDGE, batch_call.register, SCRIPTING),
        # Advanced modeling (bridge only)
        (Mode.BRIDGE, deformation.register, CORE),
        (Mode.BRIDGE, nurbs.register, CORE),
        (Mode.BRIDGE, subd.register, CORE),
        (Mode.BRIDGE, surface_match.register, CORE),
        (Mode.BRIDGE, extraction.register, CORE),
        (Mode.BRIDGE, control_points.register, CORE),
        (Mode.BRIDGE, paneling.register, BIM),
        # Display & Grasshopper (bridge only)
        (Mode.BRIDGE, display.register, CORE),
        (Mode.BRIDGE, components.register, GH),
        (Mode.BRIDGE, parameters.register, GH),
        (Mode.BRIDGE, canvas.register, GH),
        (Mode.BRIDGE, data_tree.register, GH),
        (Mode.BOTH, templates.register, GH),
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
            "Drive McNeel Rhino 8 / Rhino 9 and Grasshopper through MCP. "
            "Each tool returns structured JSON (object IDs, bounding boxes, etc.) "
            "and a short human-readable summary. Standalone mode uses rhino3dm "
            "for headless 3DM I/O; bridge mode forwards calls to a live Rhino 8 or 9 "
            "session running the rhino-mcp.rhp C# plugin."
        ),
    )

    # Always register all tool modules so BRIDGE tools remain callable even when
    # the server starts in STANDALONE mode. Lazy bridge promotion in context.py
    # handles the mode transition at call time.
    selected = toolsets_from_env(TOOLSET_GROUPS)
    applied = register_tools(
        mcp,
        Mode.BRIDGE,
        _tool_specs(),
        toolsets=selected,
        always_groups=ALWAYS_ON_GROUPS,
    )
    log.info(
        "Toolsets: %s",
        "all" if selected is None else ", ".join(sorted(selected | ALWAYS_ON_GROUPS)),
    )
    _install_bridge_retry(mcp)
    prompts = _register_prompts(mcp)
    from rhino_mcp.resources import register_resources

    resources = register_resources(mcp)
    log.info(
        "Registered %d tool modules, %d prompts and %d resources (startup_mode=%s)",
        applied,
        prompts,
        resources,
        runtime_mode.value,
    )
    return mcp, applied


def _is_unsupported(exc: BaseException) -> bool:
    from rhino_mcp.utils.error_handling import ErrorCategory, ToolError

    return isinstance(exc, ToolError) and exc.category is ErrorCategory.UNSUPPORTED


def _with_bridge_retry(fn: Callable[..., Any], is_async: bool) -> Callable[..., Any]:
    """Wrap a tool so a standalone refusal re-detects the bridge and retries once.

    Dual-mode tools pick their path from ``runtime().mode`` and raise an
    ``unsupported`` ToolError when the standalone path cannot serve the
    request. Without this wrapper they never re-detect the bridge, so a
    plug-in loaded after server start-up stays unused until a bridge-only
    tool happens to promote the runtime. Standalone paths raise that error
    before touching the document, so the retry cannot apply a change twice.
    """
    import functools

    from rhino_mcp.tools.context import runtime

    if is_async:

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            import anyio.to_thread

            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                if not _is_unsupported(exc):
                    raise
                if not await anyio.to_thread.run_sync(runtime().promote_for_bridge_only_operation):
                    raise
                log.info("Bridge became reachable; retrying %s on the bridge path", fn.__name__)
                return await fn(*args, **kwargs)

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_unsupported(exc):
                raise
            if not runtime().promote_for_bridge_only_operation():
                raise
            log.info("Bridge became reachable; retrying %s on the bridge path", fn.__name__)
            return fn(*args, **kwargs)

    return sync_wrapper


def _install_bridge_retry(mcp: FastMCP) -> None:
    """Apply :func:`_with_bridge_retry` to every registered tool."""
    for tool in mcp._tool_manager._tools.values():
        tool.fn = _with_bridge_retry(tool.fn, tool.is_async)


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
        strategy.drawing_documentation,
        strategy.quantity_takeoff,
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

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    from rhino_mcp.install import (
        add_install_subparser,
        add_uninstall_subparser,
        run_install,
        run_uninstall,
    )

    add_install_subparser(subparsers)
    add_uninstall_subparser(subparsers)

    args = parser.parse_args(argv)

    if args.command == "install":
        configure_logging()
        return run_install(args)

    if args.command == "uninstall":
        configure_logging()
        return run_uninstall(args)

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
