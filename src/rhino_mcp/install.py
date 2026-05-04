"""Claude Desktop config installer for the rhino-mcp server.

Implements the ``rhino-mcp install`` sub-command. Locates the platform-
specific ``claude_desktop_config.json`` (or accepts an explicit override),
adds or updates the ``mcpServers.<name>`` entry so it points at the
installed server, and writes a backup of the previous file. Designed to
be idempotent so running it twice is harmless.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from rhino_mcp.utils.logging import get_logger

log = get_logger("install")


SUPPORTED_MODES = ("auto", "standalone", "bridge")
SUPPORTED_TRANSPORTS = ("stdio", "http")
DEFAULT_NAME = "rhino-mcp"
DEFAULT_PYPI_DIST = "rhino3dm-mcp"


def default_config_path(platform: str | None = None) -> Path:
    """Return the platform-default Claude Desktop config path."""
    plat = platform or sys.platform
    if plat == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if plat == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def load_config(path: Path) -> dict[str, Any]:
    """Load the JSON config or return an empty skeleton."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    return json.loads(raw)


def build_server_entry(
    *,
    mode: str,
    transport: str,
    command: str,
    args: list[str],
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compose the ``mcpServers.<name>`` value."""
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"mode must be one of {SUPPORTED_MODES}; got {mode!r}")
    if transport not in SUPPORTED_TRANSPORTS:
        raise ValueError(f"transport must be one of {SUPPORTED_TRANSPORTS}; got {transport!r}")

    env: dict[str, str] = {"RHINO_MCP_TRANSPORT": transport}
    if mode != "auto":
        env["RHINO_MCP_FORCE_MODE"] = mode
    if extra_env:
        env.update(extra_env)

    return {"command": command, "args": list(args), "env": env}


def resolve_launcher(prefer: str | None = None) -> tuple[str, list[str]]:
    """Pick a launcher command + args list.

    Order: explicit ``prefer`` value -> ``uvx`` if on PATH ->
    installed ``rhino-mcp`` console-script -> ``python -m rhino_mcp.server``.
    """
    if prefer == "uvx":
        return ("uvx", [DEFAULT_PYPI_DIST])
    if prefer == "rhino-mcp":
        cmd = shutil.which("rhino-mcp") or "rhino-mcp"
        return (cmd, [])
    if prefer == "python":
        return (sys.executable, ["-m", "rhino_mcp.server"])

    uvx = shutil.which("uvx")
    if uvx:
        return (uvx, [DEFAULT_PYPI_DIST])
    rhino = shutil.which("rhino-mcp")
    if rhino:
        return (rhino, [])
    return (sys.executable, ["-m", "rhino_mcp.server"])


def merge_entry(
    config: dict[str, Any],
    name: str,
    entry: dict[str, Any],
    *,
    overwrite: bool,
) -> tuple[dict[str, Any], bool, str]:
    """Insert/update ``mcpServers.<name>``. Returns (new_config, changed, action)."""
    new = json.loads(json.dumps(config))  # deep copy via JSON round-trip
    servers = new.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("`mcpServers` in config is not an object")

    existing = servers.get(name)
    if existing is None:
        servers[name] = entry
        return new, True, "added"

    if existing == entry:
        return new, False, "unchanged"

    if not overwrite:
        return new, False, "exists"

    servers[name] = entry
    return new, True, "updated"


def write_config(path: Path, config: dict[str, Any], *, backup: bool) -> Path | None:
    """Write the config (creating parents) and return the backup path if any."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if backup and path.exists():
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_suffix(path.suffix + f".bak.{ts}")
        shutil.copy2(path, backup_path)
    serialised = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    path.write_text(serialised, encoding="utf-8")
    return backup_path


def add_install_subparser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the ``install`` sub-command."""
    parser = subparsers.add_parser(
        "install",
        help="Write the rhino-mcp entry into claude_desktop_config.json.",
        description=(
            "Add or update the rhino-mcp entry in Claude Desktop's config "
            "file so the MCP server is picked up on the next restart."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="auto",
        help="Force runtime mode (default: auto-detect on each launch).",
    )
    parser.add_argument(
        "--transport",
        choices=SUPPORTED_TRANSPORTS,
        default="stdio",
        help="MCP transport written into the env block (default: stdio).",
    )
    parser.add_argument(
        "--name",
        default=DEFAULT_NAME,
        help=f"mcpServers key to write (default: {DEFAULT_NAME}).",
    )
    parser.add_argument(
        "--launcher",
        choices=("auto", "uvx", "rhino-mcp", "python"),
        default="auto",
        help="Which command to register (default: auto-detect uvx/rhino-mcp/python).",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help="Override the Claude Desktop config path.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing entry under the same name.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip writing a timestamped .bak.* copy of the previous config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resulting config to stdout without writing the file.",
    )
    return parser


def run_install(args: argparse.Namespace) -> int:
    """Execute the ``install`` sub-command. Returns a process exit code."""
    path: Path = args.config_path or default_config_path()

    try:
        existing = load_config(path)
    except json.JSONDecodeError as exc:
        print(f"error: {path} is not valid JSON ({exc.msg})", file=sys.stderr)
        return 2

    prefer = None if args.launcher == "auto" else args.launcher
    command, cmd_args = resolve_launcher(prefer)

    entry = build_server_entry(
        mode=args.mode,
        transport=args.transport,
        command=command,
        args=cmd_args,
    )

    try:
        new_config, changed, action = merge_entry(
            existing, args.name, entry, overwrite=args.force,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if action == "exists":
        print(
            f"warning: '{args.name}' is already configured in {path}; "
            "pass --force to overwrite or --name to register under a different key.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(json.dumps(new_config, indent=2, ensure_ascii=False))
        print(f"\n# dry-run: would have {action} '{args.name}' at {path}", file=sys.stderr)
        return 0

    if not changed:
        print(f"'{args.name}' already up to date in {path}.")
        return 0

    backup_path = write_config(path, new_config, backup=not args.no_backup)

    print(f"{action} '{args.name}' in {path}")
    if backup_path:
        print(f"backup: {backup_path}")
    print("Restart Claude Desktop to pick up the change.")
    return 0
