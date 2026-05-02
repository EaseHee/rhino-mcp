"""Windows named-pipe transport.

Uses pywin32 if available, falling back to ``\\\\.\\pipe\\<name>`` accessed
through the ``open()`` builtin for plain file I/O. The bridge plugin running
inside Rhino exposes the pipe as a duplex stream.
"""

from __future__ import annotations

import os
import sys

from rhino_mcp.bridge.transport_base import Transport


def default_pipe_name() -> str:
    return os.environ.get("RHINO_MCP_PIPE", "rhino_mcp")


class NamedPipeTransport(Transport):
    def __init__(self, pipe_name: str | None = None) -> None:
        self.pipe_name = pipe_name or default_pipe_name()
        self._handle = None
        self._buffer = bytearray()

    @property
    def name(self) -> str:
        return f"pipe:\\\\.\\pipe\\{self.pipe_name}"

    def connect(self, timeout: float | None = None) -> None:
        if sys.platform != "win32":
            raise ConnectionError("Named pipes are only supported on Windows.")
        try:
            import win32file  # type: ignore[import-not-found]
            import win32pipe  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ConnectionError(
                "pywin32 is required for the named-pipe transport. "
                "Install with `pip install rhino-mcp[windows]`."
            ) from exc

        path = rf"\\.\pipe\{self.pipe_name}"
        try:
            win32pipe.WaitNamedPipe(path, int((timeout or 5) * 1000))
            self._handle = win32file.CreateFile(
                path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        except Exception as exc:  # pywin32 raises pywintypes.error
            raise ConnectionError(f"Named pipe connect to {path} failed: {exc}") from exc

    def send_line(self, payload: bytes) -> None:
        if self._handle is None:
            raise ConnectionError("NamedPipeTransport not connected")
        import win32file  # type: ignore[import-not-found]

        if not payload.endswith(b"\n"):
            payload = payload + b"\n"
        try:
            win32file.WriteFile(self._handle, payload)
        except Exception as exc:
            self._buffer.clear()
            raise ConnectionError(f"Named pipe send failed: {exc}") from exc

    def recv_line(self, timeout: float | None = None) -> bytes:
        if self._handle is None:
            raise ConnectionError("NamedPipeTransport not connected")
        import win32file  # type: ignore[import-not-found]

        try:
            while b"\n" not in self._buffer:
                err, data = win32file.ReadFile(self._handle, 4096)
                if err:
                    self._buffer.clear()
                    raise ConnectionError(f"Named pipe ReadFile error: {err}")
                if not data:
                    self._buffer.clear()
                    raise ConnectionError("Named pipe peer closed before line completion")
                self._buffer.extend(data)
        except ConnectionError:
            raise
        except Exception as exc:
            self._buffer.clear()
            raise ConnectionError(f"Named pipe recv failed: {exc}") from exc
        nl = self._buffer.index(b"\n")
        line = bytes(self._buffer[:nl])
        del self._buffer[: nl + 1]
        return line

    def close(self) -> None:
        if self._handle is not None:
            try:
                import win32file  # type: ignore[import-not-found]

                win32file.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
            self._buffer.clear()

    def is_alive(self) -> bool:
        """Non-destructive liveness probe via ``PeekNamedPipe``.

        Returns False when the handle is missing or the pipe is broken;
        returns True when the pipe handle is open (regardless of whether
        bytes are queued). Errors during the peek are treated as "dead".
        """
        if self._handle is None:
            return False
        try:
            import win32pipe  # type: ignore[import-not-found]

            # PeekNamedPipe returns (data, bytesAvail, totalBytesAvail, bytesLeft).
            # Any successful return implies the handle is still open.
            win32pipe.PeekNamedPipe(self._handle, 0)
            return True
        except Exception:
            return False
