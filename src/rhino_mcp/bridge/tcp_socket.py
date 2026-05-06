"""TCP transport. Default fallback on every platform; primary in Docker mode."""

from __future__ import annotations

import os
import socket
import sys

from rhino_mcp.bridge.transport_base import Transport


def _enable_keepalive(sock: socket.socket) -> None:
    """Enable SO_KEEPALIVE plus per-OS interval tuning when supported.

    Idle TCP connections in container/router/VPN paths are sometimes
    silently dropped after a few minutes. SO_KEEPALIVE asks the kernel to
    probe the peer; the bridge has no application-level heartbeat.
    """
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        return

    keepidle = int(os.environ.get("RHINO_MCP_KEEPALIVE_IDLE", "60"))
    keepintvl = int(os.environ.get("RHINO_MCP_KEEPALIVE_INTERVAL", "30"))
    keepcnt = int(os.environ.get("RHINO_MCP_KEEPALIVE_COUNT", "5"))

    if sys.platform == "darwin":
        TCP_KEEPALIVE = 0x10  # ``TCP_KEEPALIVE`` on macOS sets the idle interval.
        try:
            sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPALIVE, keepidle)
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        for name, value in (
            ("TCP_KEEPIDLE", keepidle),
            ("TCP_KEEPINTVL", keepintvl),
            ("TCP_KEEPCNT", keepcnt),
        ):
            opt = getattr(socket, name, None)
            if opt is None:
                continue
            try:
                sock.setsockopt(socket.IPPROTO_TCP, opt, value)
            except OSError:
                pass


class TcpTransport(Transport):
    def __init__(self, host: str = "localhost", port: int = 4242) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._buffer = bytearray()

    @property
    def name(self) -> str:
        return f"tcp://{self.host}:{self.port}"

    def connect(self, timeout: float | None = None) -> None:
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=timeout)
        except OSError as exc:
            raise ConnectionError(f"TCP connect to {self.host}:{self.port} failed: {exc}") from exc
        self._sock.settimeout(timeout)
        _enable_keepalive(self._sock)
        self._buffer.clear()

    def send_line(self, payload: bytes) -> None:
        if self._sock is None:
            raise ConnectionError("TcpTransport not connected")
        if not payload.endswith(b"\n"):
            payload = payload + b"\n"
        try:
            self._sock.sendall(payload)
        except OSError as exc:
            self._buffer.clear()
            raise ConnectionError(f"TCP send failed: {exc}") from exc

    def recv_line(self, timeout: float | None = None) -> bytes:
        if self._sock is None:
            raise ConnectionError("TcpTransport not connected")
        self._sock.settimeout(timeout)
        try:
            while b"\n" not in self._buffer:
                chunk = self._sock.recv(4096)
                if not chunk:
                    self._buffer.clear()
                    raise ConnectionError("TCP peer closed before line completion")
                self._buffer.extend(chunk)
        except TimeoutError as exc:
            self._buffer.clear()
            raise TimeoutError(f"TCP recv timed out: {exc}") from exc
        except OSError as exc:
            self._buffer.clear()
            raise ConnectionError(f"TCP recv failed: {exc}") from exc
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
        """Non-destructive liveness probe via ``MSG_PEEK``.

        - returns False when the socket is None or the peer closed
          (``recv`` would yield 0 bytes).
        - returns True when no data is pending (``BlockingIOError``) or when
          the peer has bytes queued for us.
        """
        if self._sock is None:
            return False
        # Snapshot + restore blocking state so we don't perturb caller behaviour.
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
