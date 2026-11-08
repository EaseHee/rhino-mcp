"""MCP client config installer for the rhino-mcp server.

Implements the ``rhino-mcp install`` and ``rhino-mcp uninstall``
sub-commands. Each supported MCP client (Claude Desktop, Claude Code,
Codex, Antigravity) is described by a :class:`ClientSpec` that knows
where the client keeps its config, which format it uses and how a server
entry is shaped. The installer adds, updates or removes only the
``<name>`` entry, writes a timestamped backup of the previous file and is
idempotent so running it twice is harmless.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rhino_mcp.utils.logging import get_logger

log = get_logger("install")


SUPPORTED_MODES = ("auto", "standalone", "bridge")
SUPPORTED_TRANSPORTS = ("stdio", "http")
DEFAULT_NAME = "rhino-mcp"
DEFAULT_PYPI_DIST = "rhino3dm-mcp"
DEFAULT_ROOT_KEY = "mcpServers"
DEFAULT_CLIENT = "claude-desktop"

# Result statuses printed in the per-client table.
ADDED = "added"
UPDATED = "updated"
UNCHANGED = "unchanged"
EXISTS = "exists"
REMOVED = "removed"
ABSENT = "absent"
SKIPPED = "skipped"
ERROR = "error"


class ConfigFormatError(ValueError):
    """Raised when an existing client config cannot be parsed."""


# ---------------------------------------------------------------------------
# Injectable process helpers (tests monkeypatch these)
# ---------------------------------------------------------------------------


def find_executable(name: str) -> str | None:
    """Locate a client CLI on PATH or well-known install dirs (test hook)."""
    return find_launcher_binary(name)


def run_subprocess(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run a client CLI and capture its output (indirection point for tests)."""
    return subprocess.run(
        list(cmd), capture_output=True, text=True, check=False, timeout=60,
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _home(platform: str) -> Path:
    if platform == "win32":
        profile = os.environ.get("USERPROFILE")
        if profile:
            return Path(profile)
    return Path.home()


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


def claude_code_config_path(platform: str | None = None) -> Path:
    """Return Claude Code's user-scope config (``~/.claude.json``)."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override) / ".claude.json"
    return _home(platform or sys.platform) / ".claude.json"


def codex_config_path(platform: str | None = None) -> Path:
    """Return Codex's ``config.toml`` (``$CODEX_HOME`` wins over ``~/.codex``)."""
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "config.toml"
    return _home(platform or sys.platform) / ".codex" / "config.toml"


def antigravity_config_path(platform: str | None = None) -> Path:
    """Return Antigravity's ``mcp_config.json``."""
    return _home(platform or sys.platform) / ".gemini" / "antigravity" / "mcp_config.json"


# ---------------------------------------------------------------------------
# Client table
# ---------------------------------------------------------------------------


def _shape_plain(entry: dict[str, Any]) -> dict[str, Any]:
    return {"command": entry["command"], "args": list(entry["args"]), "env": dict(entry["env"])}


def _shape_claude_code(entry: dict[str, Any]) -> dict[str, Any]:
    return {"type": "stdio", **_shape_plain(entry)}


@dataclass(frozen=True)
class ClientSpec:
    """Static description of one MCP client."""

    name: str
    label: str
    path_fn: Callable[[str | None], Path]
    fmt: str  # "json" or "toml"
    root_key: str
    shape: Callable[[dict[str, Any]], dict[str, Any]]
    cli: str | None = None
    detect_paths: Callable[[Path], tuple[Path, ...]] | None = None

    def config_path(self, platform: str | None = None) -> Path:
        return self.path_fn(platform)

    def detected(self, path: Path | None = None) -> bool:
        p = path or self.config_path()
        candidates = self.detect_paths(p) if self.detect_paths else (p, p.parent)
        if any(c.exists() for c in candidates):
            return True
        return bool(self.cli and find_executable(self.cli))


CLIENTS: dict[str, ClientSpec] = {
    "claude-desktop": ClientSpec(
        name="claude-desktop",
        label="Claude Desktop",
        path_fn=default_config_path,
        fmt="json",
        root_key="mcpServers",
        shape=_shape_plain,
    ),
    "claude-code": ClientSpec(
        name="claude-code",
        label="Claude Code",
        path_fn=claude_code_config_path,
        fmt="json",
        root_key="mcpServers",
        shape=_shape_claude_code,
        cli="claude",
        # The parent of ~/.claude.json is the home dir, so probe ~/.claude/ instead.
        detect_paths=lambda p: (p, p.parent / ".claude"),
    ),
    "codex": ClientSpec(
        name="codex",
        label="Codex",
        path_fn=codex_config_path,
        fmt="toml",
        root_key="mcp_servers",
        shape=_shape_plain,
        cli="codex",
    ),
    "antigravity": ClientSpec(
        name="antigravity",
        label="Antigravity",
        path_fn=antigravity_config_path,
        fmt="json",
        root_key="mcpServers",
        shape=_shape_plain,
    ),
}

CLIENT_CHOICES = (*CLIENTS.keys(), "all", "detected")


# ---------------------------------------------------------------------------
# Entry construction
# ---------------------------------------------------------------------------


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


def uvx_args() -> list[str]:
    """uvx arguments that never fall back to a cached server older than this one."""
    from rhino_mcp import __version__

    return ["--from", f"{DEFAULT_PYPI_DIST}>={__version__}", DEFAULT_PYPI_DIST]


def _uvx_serves_this_version(uvx: str) -> bool:
    """True when uvx can run a server at least as new as this one, i.e. it is on PyPI."""
    try:
        proc = subprocess.run(
            [uvx, *uvx_args(), "--version"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _own_console_script() -> str | None:
    """The ``rhino-mcp`` script installed with the running interpreter, if any."""
    exe = Path(sys.executable)
    for name in ("rhino-mcp", "rhino-mcp.exe"):
        candidate = exe.with_name(name)
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_launcher(prefer: str | None = None) -> tuple[str, list[str]]:
    """Pick a launcher command + args list.

    Explicit ``prefer`` values are honoured. In auto mode ``uvx`` is used only
    when PyPI already serves this version; otherwise the entry points at this
    very installation (its ``rhino-mcp`` script, or ``python -m``), so a
    client never starts an older server than the one that wrote its config.
    A ``rhino-mcp`` found elsewhere on PATH may be stale, so it is only used
    when asked for explicitly and this installation has no script of its own.
    """
    if prefer == "uvx":
        return (find_launcher_binary("uvx") or "uvx", uvx_args())
    if prefer == "rhino-mcp":
        return (_own_console_script() or find_launcher_binary("rhino-mcp") or "rhino-mcp", [])
    if prefer == "python":
        return (sys.executable, ["-m", "rhino_mcp.server"])

    uvx = find_launcher_binary("uvx")
    if uvx and _uvx_serves_this_version(uvx):
        return (uvx, uvx_args())
    own = _own_console_script()
    if own:
        return (own, [])
    return (sys.executable, ["-m", "rhino_mcp.server"])


# GUI-launched processes (Rhino, Claude Desktop) often miss the user's shell
# PATH, so also probe the default install locations of uv / pipx / Homebrew.
_LAUNCHER_FALLBACK_DIRS = (
    "~/.local/bin",
    "~/.cargo/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
)


def find_launcher_binary(name: str) -> str | None:
    """Return an absolute path for ``name`` from PATH or well-known install dirs.

    The config is read by MCP clients whose PATH may differ from ours, so a
    bare command name is only used when no absolute path can be found.
    """
    found = shutil.which(name)
    if found:
        return found
    suffixes = (".exe", ".cmd", "") if sys.platform == "win32" else ("",)
    for directory in _LAUNCHER_FALLBACK_DIRS:
        base = Path(directory).expanduser()
        for suffix in suffixes:
            candidate = base / f"{name}{suffix}"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


# ---------------------------------------------------------------------------
# JSON configs
# ---------------------------------------------------------------------------


def load_config(path: Path) -> dict[str, Any]:
    """Load the JSON config or return an empty skeleton."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


# Env keys the installer owns; every other env key is user-managed and kept.
OWNED_ENV_KEYS = frozenset({"RHINO_MCP_TRANSPORT", "RHINO_MCP_FORCE_MODE"})


def merge_server_entry(existing: Any, entry: dict[str, Any]) -> dict[str, Any]:
    """Overlay ``entry`` on ``existing`` keeping user-added keys and env vars."""
    if not isinstance(existing, dict):
        fresh: dict[str, Any] = copy.deepcopy(entry)
        return fresh
    merged: dict[str, Any] = copy.deepcopy(existing)
    for key, value in entry.items():
        if key == "env" and isinstance(value, dict):
            old_env = merged.get("env")
            env = {
                k: v for k, v in (old_env.items() if isinstance(old_env, dict) else ())
                if k not in OWNED_ENV_KEYS
            }
            env.update(value)
            merged["env"] = env
        else:
            merged[key] = value
    return merged


def merge_entry(
    config: dict[str, Any],
    name: str,
    entry: dict[str, Any],
    *,
    overwrite: bool,
    root_key: str = DEFAULT_ROOT_KEY,
) -> tuple[dict[str, Any], bool, str]:
    """Insert/update ``<root_key>.<name>``. Returns (new_config, changed, action)."""
    new = copy.deepcopy(config)
    servers = new.setdefault(root_key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"`{root_key}` in config is not an object")

    existing = servers.get(name)
    if existing is None:
        servers[name] = entry
        return new, True, ADDED

    merged = merge_server_entry(existing, entry)
    if existing == merged:
        return new, False, UNCHANGED

    if not overwrite:
        return new, False, EXISTS

    servers[name] = merged
    return new, True, UPDATED


def remove_entry(
    config: dict[str, Any],
    name: str,
    *,
    root_key: str = DEFAULT_ROOT_KEY,
) -> tuple[dict[str, Any], bool]:
    """Drop ``<root_key>.<name>``. Returns (new_config, removed)."""
    new = copy.deepcopy(config)
    servers = new.get(root_key)
    if servers is None:
        return new, False
    if not isinstance(servers, dict):
        raise ValueError(f"`{root_key}` in config is not an object")
    if name not in servers:
        return new, False
    del servers[name]
    return new, True


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_suffix(path.suffix + f".bak.{ts}")
    # Two runs in the same second must not overwrite the earlier (original) backup.
    n = 1
    while backup_path.exists():
        backup_path = path.with_suffix(path.suffix + f".bak.{ts}-{n}")
        n += 1
    shutil.copy2(path, backup_path)
    return backup_path


def write_text_config(path: Path, text: str, *, backup: bool) -> Path | None:
    """Write raw config text (creating parents); return the backup path if any."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = _backup(path) if backup else None
    path.write_text(text, encoding="utf-8")
    return backup_path


def _dump_json(config: dict[str, Any]) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def write_config(path: Path, config: dict[str, Any], *, backup: bool) -> Path | None:
    """Write the JSON config (creating parents) and return the backup path if any."""
    return write_text_config(path, _dump_json(config), backup=backup)


# ---------------------------------------------------------------------------
# TOML configs (Codex) — textual table replacement, no new dependency
# ---------------------------------------------------------------------------

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def toml_string(value: str) -> str:
    """Serialise a TOML basic string with full escaping."""
    out = ['"']
    for ch in value:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\r":
            out.append("\\r")
        elif code < 0x20 or code == 0x7F:
            out.append(f"\\u{code:04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def toml_key(key: str) -> str:
    """Return ``key`` bare when allowed, otherwise as a quoted basic string."""
    return key if _BARE_KEY.match(key) else toml_string(key)


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return toml_string(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{toml_key(k)} = {_toml_value(v)}" for k, v in value.items()) + "}"
    # tomllib yields datetime/date/time for TOML date-times; their ISO form is valid TOML.
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    raise ValueError(f"unsupported TOML value: {value!r}; edit the entry manually")


def render_toml_table(root_key: str, name: str, entry: dict[str, Any]) -> str:
    """Render ``[root.name]`` with scalar keys and nested dicts as sub-tables."""
    prefix = f"{toml_key(root_key)}.{toml_key(name)}"
    lines = [f"[{prefix}]"]
    subtables: list[tuple[str, dict[str, Any]]] = []
    for key, value in entry.items():
        if isinstance(value, dict):
            subtables.append((key, value))
        else:
            lines.append(f"{toml_key(key)} = {_toml_value(value)}")
    for key, table in subtables:
        lines.append("")
        lines.append(f"[{prefix}.{toml_key(key)}]")
        for k, v in table.items():
            lines.append(f"{toml_key(k)} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def parse_table_header(line: str) -> list[str] | None:
    """Return the key parts when ``line`` is a ``[table]`` / ``[[array]]`` header."""
    text = line.strip()
    if not text.startswith("["):
        return None
    double = text.startswith("[[")
    parsed = _parse_key_at(text, 2 if double else 1)
    if parsed is None:
        return None
    parts, i = parsed
    closing = "]]" if double else "]"
    if not text.startswith(closing, i):
        return None
    rest = text[i + len(closing):].strip()
    if rest and not rest.startswith("#"):
        return None
    return parts


def _parse_key_at(raw: str, i: int) -> tuple[list[str], int] | None:
    """Parse a dotted key from ``raw[i:]``; return (parts, index after trailing ws)."""
    parts: list[str] = []
    n = len(raw)
    while True:
        while i < n and raw[i] in " \t":
            i += 1
        if i >= n:
            return None
        if raw[i] == '"':
            j = i + 1
            buf: list[str] = []
            while j < n and raw[j] != '"':
                if raw[j] == "\\" and j + 1 < n:
                    buf.append(raw[j : j + 2])
                    j += 2
                    continue
                buf.append(raw[j])
                j += 1
            if j >= n:
                return None
            try:
                parts.append(tomllib.loads(f'k = "{"".join(buf)}"')["k"])
            except tomllib.TOMLDecodeError:
                return None
            i = j + 1
        elif raw[i] == "'":
            j = raw.find("'", i + 1)
            if j < 0:
                return None
            parts.append(raw[i + 1 : j])
            i = j + 1
        else:
            j = i
            while j < n and (raw[j].isalnum() or raw[j] in "_-"):
                j += 1
            if j == i:
                return None
            parts.append(raw[i:j])
            i = j
        while i < n and raw[i] in " \t":
            i += 1
        if i >= n or raw[i] != ".":
            return parts, i
        i += 1


def _header_lines(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Return (line index, key parts) of every table header outside multi-line strings."""
    headers: list[tuple[int, list[str]]] = []
    in_multiline: str | None = None
    for idx, line in enumerate(lines):
        if in_multiline is None:
            key = parse_table_header(line)
            if key is not None:
                headers.append((idx, key))
                continue
        for delim in ('"""', "'''"):
            count = line.count(delim)
            if in_multiline is None and count % 2 == 1:
                in_multiline = delim
                break
            if in_multiline == delim and count % 2 == 1:
                in_multiline = None
                break
    return headers


def _find_table_block(lines: list[str], root_key: str, name: str) -> tuple[int, int] | None:
    """Locate ``[root.name]`` and its sub-tables as a [start, end) line range."""
    prefix = [root_key, name]
    headers = _header_lines(lines)
    start: int | None = None
    end = len(lines)
    for idx, key in headers:
        ours = key[:2] == prefix
        if start is None:
            if ours:
                start = idx
        elif not ours:
            end = idx
            break
    if start is None:
        return None
    # Leave trailing blanks/comments attached to the following header.
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return start, end


def load_toml_config(path: Path) -> tuple[str, dict[str, Any]]:
    """Return (raw text, parsed data) of a TOML config; empty when missing."""
    if not path.exists():
        return "", {}
    raw = path.read_text(encoding="utf-8")
    try:
        return raw, tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigFormatError(f"{path} is not valid TOML ({exc})") from exc


def _toml_servers(data: dict[str, Any], root_key: str) -> dict[str, Any]:
    servers = data.get(root_key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"`{root_key}` in config is not a table")
    return servers


def toml_upsert(
    raw: str, root_key: str, name: str, entry: dict[str, Any]
) -> str:
    """Return ``raw`` with the ``[root.name]`` block replaced or appended."""
    lines = raw.splitlines(keepends=True)
    block = render_toml_table(root_key, name, entry)
    span = _find_table_block(lines, root_key, name)
    if span is None:
        if name in _toml_servers(tomllib.loads(raw) if raw else {}, root_key):
            raise ValueError(
                f"`{root_key}.{name}` is defined inline or with dotted keys; edit it manually"
            )
        text = raw
        if text and not text.endswith("\n"):
            text += "\n"
        if text.strip():
            text += "\n"
        result = text + block
    else:
        start, end = span
        tail = "".join(lines[end:])
        sep = "\n" if tail and not tail.startswith(("\n", "\r\n")) else ""
        result = "".join(lines[:start]) + block + sep + tail
    _verify_toml(result, root_key, name, entry)
    return result


def toml_remove(raw: str, root_key: str, name: str) -> str:
    """Return ``raw`` without the ``[root.name]`` block."""
    lines = raw.splitlines(keepends=True)
    span = _find_table_block(lines, root_key, name)
    if span is None:
        raise ValueError(
            f"`{root_key}.{name}` is defined inline or with dotted keys; edit it manually"
        )
    start, end = span
    head = "".join(lines[:start])
    tail = "".join(lines[end:])
    if not head.strip():
        tail = tail.lstrip("\n")
    elif not tail.strip():
        head = head.rstrip("\r\n") + "\n"
        tail = ""
    elif head.endswith("\n\n") and tail.startswith("\n"):
        tail = tail[1:]
    result = head + tail
    _verify_toml(result, root_key, name, None)
    return result


def _verify_toml(text: str, root_key: str, name: str, entry: dict[str, Any] | None) -> None:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"edit would produce invalid TOML ({exc}); config left untouched") from exc
    actual = _toml_servers(data, root_key).get(name)
    if actual != entry:
        raise ValueError("edit did not round-trip; config left untouched")


# ---------------------------------------------------------------------------
# Per-client operations
# ---------------------------------------------------------------------------


@dataclass
class ClientResult:
    client: ClientSpec
    status: str
    path: Path
    detail: str = ""
    backup: Path | None = None
    preview: str | None = None
    invalid: bool = False


def _existing_entry(spec: ClientSpec, path: Path, name: str) -> Any:
    """Return the current ``name`` entry for ``spec`` (None when absent)."""
    if spec.fmt == "toml":
        _, data = load_toml_config(path)
        return _toml_servers(data, spec.root_key).get(name)
    try:
        cfg = load_config(path)
    except json.JSONDecodeError as exc:
        raise ConfigFormatError(f"{path} is not valid JSON ({exc.msg})") from exc
    servers = cfg.get(spec.root_key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"`{spec.root_key}` in config is not an object")
    return servers.get(name)


def installed_state(spec: ClientSpec, path: Path, name: str) -> tuple[bool, str | None]:
    """Return (installed, error message when the config cannot be read)."""
    try:
        return _existing_entry(spec, path, name) is not None, None
    except (ValueError, OSError) as exc:
        return False, str(exc)


def is_installed(spec: ClientSpec, path: Path, name: str) -> bool:
    return installed_state(spec, path, name)[0]


def _use_claude_cli(spec: ClientSpec, explicit_path: bool) -> str | None:
    if spec.cli is None or spec.name != "claude-code" or explicit_path:
        return None
    return find_executable(spec.cli)


def _claude_add_cmd(cli: str, name: str, entry: Any) -> list[str]:
    return [cli, "mcp", "add-json", "--scope", "user", name, json.dumps(entry, ensure_ascii=False)]


def _cli_failure(proc: subprocess.CompletedProcess[str]) -> str:
    msg = (proc.stderr or proc.stdout or "").strip().splitlines()
    return msg[-1] if msg else f"exit code {proc.returncode}"


def install_client(
    spec: ClientSpec,
    path: Path,
    name: str,
    base_entry: dict[str, Any],
    *,
    overwrite: bool,
    backup: bool,
    dry_run: bool,
    explicit_path: bool,
) -> ClientResult:
    entry = spec.shape(base_entry)
    try:
        if spec.fmt == "toml":
            raw, data = load_toml_config(path)
            existing = _toml_servers(data, spec.root_key).get(name)
            target = entry if existing is None else merge_server_entry(existing, entry)
            if existing == target:
                return ClientResult(spec, UNCHANGED, path)
            if existing is not None and not overwrite:
                return ClientResult(spec, EXISTS, path, "pass --force to overwrite")
            action = ADDED if existing is None else UPDATED
            text = toml_upsert(raw, spec.root_key, name, target)
            if dry_run:
                return ClientResult(spec, action, path, "dry-run", preview=text)
            bak = write_text_config(path, text, backup=backup)
            return ClientResult(spec, action, path, backup=bak)

        try:
            config = load_config(path)
        except json.JSONDecodeError as exc:
            raise ConfigFormatError(f"{path} is not valid JSON ({exc.msg})") from exc
        new_config, changed, action = merge_entry(
            config, name, entry, overwrite=overwrite, root_key=spec.root_key,
        )
        if action == EXISTS:
            return ClientResult(spec, EXISTS, path, "pass --force to overwrite")
        if not changed:
            return ClientResult(spec, UNCHANGED, path)

        cli = _use_claude_cli(spec, explicit_path)
        if cli:
            target = new_config[spec.root_key][name]
            previous = config.get(spec.root_key, {}).get(name)
            remove_cmd = [cli, "mcp", "remove", "--scope", "user", name]
            add_cmd = _claude_add_cmd(cli, name, target)
            cmds = [remove_cmd, add_cmd] if action == UPDATED else [add_cmd]
            if dry_run:
                preview = "\n".join(" ".join(c) for c in cmds) + "\n"
                return ClientResult(spec, action, path, "dry-run (claude CLI)", preview=preview)
            bak = _backup(path) if backup else None
            if action == UPDATED:
                proc = run_subprocess(remove_cmd)
                if proc.returncode != 0:
                    return ClientResult(spec, ERROR, path, f"claude CLI: {_cli_failure(proc)}", backup=bak)
            proc = run_subprocess(add_cmd)
            if proc.returncode != 0:
                detail = f"claude CLI: {_cli_failure(proc)}"
                if action == UPDATED:
                    restore = run_subprocess(_claude_add_cmd(cli, name, previous))
                    detail += (
                        "; previous entry restored"
                        if restore.returncode == 0
                        else "; previous entry removed and restore failed"
                    )
                return ClientResult(spec, ERROR, path, detail, backup=bak)
            return ClientResult(spec, action, path, "via claude CLI", backup=bak)

        if dry_run:
            return ClientResult(spec, action, path, "dry-run", preview=_dump_json(new_config))
        bak = write_config(path, new_config, backup=backup)
        return ClientResult(spec, action, path, backup=bak)
    except ConfigFormatError as exc:
        return ClientResult(spec, ERROR, path, str(exc), invalid=True)
    except (ValueError, TypeError, OSError, subprocess.SubprocessError) as exc:
        return ClientResult(spec, ERROR, path, str(exc))


def uninstall_client(
    spec: ClientSpec,
    path: Path,
    name: str,
    *,
    backup: bool,
    dry_run: bool,
    explicit_path: bool,
) -> ClientResult:
    try:
        if spec.fmt == "toml":
            raw, data = load_toml_config(path)
            if name not in _toml_servers(data, spec.root_key):
                return ClientResult(spec, ABSENT, path)
            text = toml_remove(raw, spec.root_key, name)
            if dry_run:
                return ClientResult(spec, REMOVED, path, "dry-run", preview=text)
            bak = write_text_config(path, text, backup=backup)
            return ClientResult(spec, REMOVED, path, backup=bak)

        try:
            config = load_config(path)
        except json.JSONDecodeError as exc:
            raise ConfigFormatError(f"{path} is not valid JSON ({exc.msg})") from exc
        new_config, removed = remove_entry(config, name, root_key=spec.root_key)
        if not removed:
            return ClientResult(spec, ABSENT, path)

        cli = _use_claude_cli(spec, explicit_path)
        if cli:
            cmd = [cli, "mcp", "remove", "--scope", "user", name]
            if dry_run:
                return ClientResult(spec, REMOVED, path, "dry-run (claude CLI)", preview=" ".join(cmd) + "\n")
            bak = _backup(path) if backup else None
            proc = run_subprocess(cmd)
            if proc.returncode != 0:
                return ClientResult(spec, ERROR, path, f"claude CLI: {_cli_failure(proc)}", backup=bak)
            return ClientResult(spec, REMOVED, path, "via claude CLI", backup=bak)

        if dry_run:
            return ClientResult(spec, REMOVED, path, "dry-run", preview=_dump_json(new_config))
        bak = write_config(path, new_config, backup=backup)
        return ClientResult(spec, REMOVED, path, backup=bak)
    except ConfigFormatError as exc:
        return ClientResult(spec, ERROR, path, str(exc), invalid=True)
    except (ValueError, TypeError, OSError, subprocess.SubprocessError) as exc:
        return ClientResult(spec, ERROR, path, str(exc))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--client",
        action="append",
        choices=CLIENT_CHOICES,
        default=None,
        metavar="CLIENT",
        help=(
            "Target MCP client; repeatable. One of "
            f"{', '.join(CLIENT_CHOICES)} (default: {DEFAULT_CLIENT})."
        ),
    )
    parser.add_argument(
        "--name",
        default=DEFAULT_NAME,
        help=f"Server key to write or remove (default: {DEFAULT_NAME}).",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help="Override the config path (only with a single concrete --client).",
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


def add_install_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
) -> argparse.ArgumentParser:
    """Register the ``install`` sub-command."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "install",
        help="Register rhino-mcp in MCP client configs (Claude Desktop, Claude Code, Codex, Antigravity).",
        description=(
            "Add or update the rhino-mcp entry in the config of one or more MCP "
            "clients so the server is picked up on the next client restart."
        ),
    )
    _add_client_args(parser)
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
        "--launcher",
        choices=("auto", "uvx", "rhino-mcp", "python"),
        default="auto",
        help="Which command to register (default: auto-detect uvx/rhino-mcp/python).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing entry under the same name.",
    )
    parser.add_argument(
        "--list-clients",
        action="store_true",
        help="List supported clients with detection/installation state and exit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --list-clients, emit machine-readable JSON.",
    )
    return parser


def add_uninstall_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
) -> argparse.ArgumentParser:
    """Register the ``uninstall`` sub-command."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "uninstall",
        help="Remove the rhino-mcp entry from MCP client configs.",
        description=(
            "Remove only the rhino-mcp entry (other servers are kept) from the "
            "config of one or more MCP clients, backing up the previous file."
        ),
    )
    _add_client_args(parser)
    return parser


def _resolve_targets(
    requested: list[str] | None, config_path: Path | None
) -> tuple[list[ClientSpec], str | None]:
    names = requested or [DEFAULT_CLIENT]
    concrete = [n for n in names if n in CLIENTS]
    if config_path is not None and (len(set(names)) != 1 or not concrete):
        return [], "--config-path requires exactly one concrete --client"

    selected: list[str] = []
    for n in names:
        if n == "all":
            expanded = list(CLIENTS)
        elif n == "detected":
            expanded = [c for c, spec in CLIENTS.items() if spec.detected()]
        else:
            expanded = [n]
        for c in expanded:
            if c not in selected:
                selected.append(c)
    if not selected:
        return [], "no supported MCP clients detected; pass --client explicitly"
    return [CLIENTS[c] for c in selected], None


def _print_results(results: list[ClientResult], name: str, *, to_stderr: bool) -> None:
    stream = sys.stderr if to_stderr else sys.stdout
    width = max(len(r.client.label) for r in results)
    print(f"rhino-mcp entry '{name}':", file=stream)
    for r in results:
        line = f"  {r.client.label:<{width}}  {r.status:<9}  {r.path}"
        if r.detail:
            line += f"  ({r.detail})"
        print(line, file=stream)
        if r.backup:
            print(f"  {'':<{width}}  {'backup':<9}  {r.backup}", file=stream)


def _print_previews(results: list[ClientResult]) -> None:
    previews = [r for r in results if r.preview is not None]
    for r in previews:
        if len(previews) > 1:
            print(f"# --- {r.client.label}: {r.path}")
        sys.stdout.write(r.preview or "")


def _exit_code(results: list[ClientResult]) -> int:
    if any(r.invalid for r in results):
        return 2
    if any(r.status in (ERROR, EXISTS) for r in results):
        return 1
    return 0


def _restart_hint(results: list[ClientResult]) -> None:
    changed = [r.client.label for r in results if r.status in (ADDED, UPDATED, REMOVED)]
    if changed:
        print(f"Restart {', '.join(changed)} to pick up the change.")


def list_clients(name: str, *, as_json: bool) -> int:
    rows: list[dict[str, Any]] = []
    for spec in CLIENTS.values():
        path = spec.config_path()
        installed, error = installed_state(spec, path, name)
        row: dict[str, Any] = {
            "name": spec.name,
            "label": spec.label,
            "path": str(path),
            "detected": spec.detected(path),
            "installed": installed,
        }
        if error is not None:
            row["error"] = error
        rows.append(row)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    width = max(len(r["name"]) for r in rows)
    print(f"{'client':<{width}}  detected  installed  path")
    for r in rows:
        det = "yes" if r["detected"] else "no"
        inst = "error" if "error" in r else ("yes" if r["installed"] else "no")
        line = f"{r['name']:<{width}}  {det:<8}  {inst:<9}  {r['path']}"
        if "error" in r:
            line += f"  ({r['error']})"
        print(line)
    return 0


def run_install(args: argparse.Namespace) -> int:
    """Execute the ``install`` sub-command. Returns a process exit code."""
    if args.list_clients:
        return list_clients(args.name, as_json=args.json)

    targets, err = _resolve_targets(args.client, args.config_path)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    prefer = None if args.launcher == "auto" else args.launcher
    command, cmd_args = resolve_launcher(prefer)
    try:
        base_entry = build_server_entry(
            mode=args.mode, transport=args.transport, command=command, args=cmd_args,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = [
        install_client(
            spec,
            args.config_path or spec.config_path(),
            args.name,
            base_entry,
            overwrite=args.force,
            backup=not args.no_backup,
            dry_run=args.dry_run,
            explicit_path=args.config_path is not None,
        )
        for spec in targets
    ]
    return _report(results, args.name, dry_run=args.dry_run)


def run_uninstall(args: argparse.Namespace) -> int:
    """Execute the ``uninstall`` sub-command. Returns a process exit code."""
    targets, err = _resolve_targets(args.client, args.config_path)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    results = [
        uninstall_client(
            spec,
            args.config_path or spec.config_path(),
            args.name,
            backup=not args.no_backup,
            dry_run=args.dry_run,
            explicit_path=args.config_path is not None,
        )
        for spec in targets
    ]
    return _report(results, args.name, dry_run=args.dry_run)


def _report(results: list[ClientResult], name: str, *, dry_run: bool) -> int:
    if dry_run:
        _print_previews(results)
    _print_results(results, name, to_stderr=dry_run)
    if any(r.status == EXISTS for r in results):
        print(
            f"warning: '{name}' is already configured with different settings; "
            "pass --force to overwrite or --name to register under a different key.",
            file=sys.stderr,
        )
    if not dry_run:
        _restart_hint(results)
    return _exit_code(results)
