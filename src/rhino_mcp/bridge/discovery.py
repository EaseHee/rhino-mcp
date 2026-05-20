"""Discover live Rhino bridge instances via per-process announcement files.

The C# plugin (``AnnouncementWriter``) writes a JSON file per running Rhino
session to a well-known directory. This module reads that directory, prunes
stale entries (dead PID or unreachable port), and exposes the survivors so the
MCP server can target a specific Rhino when several are running side-by-side.

Listener directory resolution (must match ``AnnouncementWriter.ResolveListenerDir``):

- ``RHINO_MCP_LISTENER_DIR`` (explicit override) wins.
- Windows: ``%LOCALAPPDATA%/rhino-mcp/listeners``.
- macOS / Linux: ``${TMPDIR:-/tmp}/rhino-mcp-listeners``.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rhino_mcp.utils.logging import get_logger

log = get_logger("discovery")


@dataclass
class InstanceInfo:
    """One live (or stale) Rhino bridge endpoint discovered on this host."""

    pid: int
    host: str
    port: int
    doc_path: str
    doc_title: str
    rhino_version: str
    protocol_version: str
    started_at: str
    file_path: str
    alive: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def listener_dir() -> Path:
    """Resolve the listener directory; mirrors the C# side."""
    explicit = os.environ.get("RHINO_MCP_LISTENER_DIR", "").strip()
    if explicit:
        return Path(explicit)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "rhino-mcp" / "listeners"
    tmp = os.environ.get("TMPDIR", "/tmp").rstrip("/")
    return Path(tmp) / "rhino-mcp-listeners"


def _pid_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` exists on this host."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # Best-effort: open the process for query-limited information.
        try:
            import ctypes  # local import to avoid Windows-only dependency at module load

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        except Exception:
            return True  # fail-open; caller still does a TCP probe
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # the process exists, we just can't signal it
    except OSError:
        return False


def _port_alive(host: str, port: int, timeout: float = 0.5) -> bool:
    """Cheap TCP connectivity check; no protocol exchange."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def list_rhino_instances(
    *,
    stale_cleanup: bool = True,
    probe_timeout: float = 0.5,
) -> list[InstanceInfo]:
    """Return every announcement file in ``listener_dir()``.

    When ``stale_cleanup`` is True, files whose PID is gone are removed from
    disk after evaluation. The TCP probe just verifies the port accepts; full
    ``rhino.ping`` validation is the caller's responsibility (typically via
    ``BridgeClient.auto``).
    """
    out: list[InstanceInfo] = []
    base = listener_dir()
    if not base.exists():
        return out
    for entry in sorted(base.glob("*.json")):
        try:
            raw = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.debug("Skipping unreadable announcement %s: %s", entry, exc)
            continue
        try:
            pid = int(raw.get("pid", 0))
            port = int(raw.get("port", 0))
            host = str(raw.get("host", "127.0.0.1"))
        except (TypeError, ValueError):
            log.debug("Skipping malformed announcement %s", entry)
            continue
        pid_ok = _pid_alive(pid)
        port_ok = pid_ok and _port_alive(host, port, timeout=probe_timeout)
        info = InstanceInfo(
            pid=pid,
            host=host,
            port=port,
            doc_path=str(raw.get("doc_path", "")),
            doc_title=str(raw.get("doc_title", "")),
            rhino_version=str(raw.get("rhino_version", "")),
            protocol_version=str(raw.get("protocol_version", "")),
            started_at=str(raw.get("started_at", "")),
            file_path=str(entry),
            alive=port_ok,
        )
        if not pid_ok and stale_cleanup:
            try:
                entry.unlink()
                log.info("Removed stale announcement %s (pid %d gone)", entry, pid)
                continue
            except OSError:
                pass
        out.append(info)
    return out


def select_endpoint(
    *,
    pid: int | None = None,
    port: int | None = None,
    doc_path_contains: str | None = None,
    index: int | None = None,
) -> InstanceInfo | None:
    """Pick a single instance from discovery results.

    Selectors are evaluated in order: ``pid`` → ``port`` → ``doc_path_contains``
    → ``index`` (zero-based into the alive list). Returns ``None`` when no
    candidate matches.
    """
    instances = [i for i in list_rhino_instances() if i.alive]
    if not instances:
        return None
    if pid is not None:
        return next((i for i in instances if i.pid == pid), None)
    if port is not None:
        return next((i for i in instances if i.port == port), None)
    if doc_path_contains is not None:
        needle = doc_path_contains.lower()
        return next(
            (i for i in instances if needle in i.doc_path.lower() or needle in i.doc_title.lower()),
            None,
        )
    if index is not None and 0 <= index < len(instances):
        return instances[index]
    return None


def apply_endpoint(info: InstanceInfo) -> None:
    """Point the next bridge connection at ``info`` by setting RHINO_HOST/PORT.

    The runtime's lazy promotion path (``Runtime.require_bridge``) will pick
    these up the next time it needs to reconnect.
    """
    os.environ["RHINO_HOST"] = info.host
    os.environ["RHINO_PORT"] = str(info.port)
    log.info("Switched bridge endpoint → %s:%d (pid=%d, %s)", info.host, info.port, info.pid, info.doc_title or "<untitled>")


def now_iso() -> str:
    """Helper for tests that need a deterministic timestamp shape."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
