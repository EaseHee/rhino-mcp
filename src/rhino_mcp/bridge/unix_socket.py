"""Unix domain socket transport (macOS/Linux primary)."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from rhino_mcp.bridge.transport_base import Transport


def default_socket_path() -> Path:
    """Resolve the default socket location.

    Honours ``RHINO_MCP_SOCKET`` if set; otherwise prefers
    ``$XDG_RUNTIME_DIR/rhino_mcp.sock`` and falls back to ``/tmp/rhino_mcp.sock``.
    """
    explicit = os.environ.get("RHINO_MCP_SOCKET")
    if explicit:
        return Path(explicit)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "rhino_mcp.sock"
    return Path("/tmp/rhino_mcp.sock")


class UnixSocketTransport(Transport):
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_socket_path()
        self._sock: socket.socket | None = None
        self._buffer = bytearray()

    @property
    def name(self) -> str:
        return f"unix://{self.path}"

    def connect(self, timeout: float | None = None) -> None:
        if not self.path.exists():
            raise ConnectionError(
                f"Unix socket {self.path} does not exist. "
                "Load the rhino-mcp.rhp C# plugin in Rhino 8 first."
            )
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(str(self.path))
        except OSError as exc:
            raise ConnectionError(f"Unix socket connect to {self.path} failed: {exc}") from exc
        self._sock = s

    def send_line(self, payload: bytes) -> None:
        if self._sock is None:
            raise ConnectionError("UnixSocketTransport not connected")
        if not payload.endswith(b"\n"):
            payload = payload + b"\n"
        try:
            self._sock.sendall(payload)
        except OSError as exc:
            self._buffer.clear()
            raise ConnectionError(f"Unix socket send failed: {exc}") from exc

    def recv_line(self, timeout: float | None = None) -> bytes:
        if self._sock is None:
            raise ConnectionError("UnixSocketTransport not connected")
        self._sock.settimeout(timeout)
        try:
            while b"\n" not in self._buffer:
                chunk = self._sock.recv(4096)
                if not chunk:
                    self._buffer.clear()
                    raise ConnectionError("Unix socket peer closed before line completion")
                self._buffer.extend(chunk)
        except TimeoutError as exc:
            self._buffer.clear()
            raise TimeoutError(f"Unix socket recv timed out: {exc}") from exc
        except OSError as exc:
            self._buffer.clear()
            raise ConnectionError(f"Unix socket recv failed: {exc}") from exc
        nl = self._buffer.index(b"\n")
        line = bytes(self._buffer[:nl])
        del self._buffer[: nl + 1]
        return line

    def reset_buffers(self) -> None:
        self._buffer.clear()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None
            self._buffer.clear()

    def is_alive(self) -> bool:
        """Non-destructive liveness probe via ``MSG_PEEK`` (matches TCP behaviour)."""
        if self._sock is None:
            return False
        was_blocking = self._sock.getblocking()
        try:
            self._sock.setblocking(False)
            try:
                data = self._sock.recv(1, socket.MSG_PEEK)
            except BlockingIOError:
                return True
            except OSError:
                return False
            return bool(data)
        finally:
            self._sock.setblocking(was_blocking)
