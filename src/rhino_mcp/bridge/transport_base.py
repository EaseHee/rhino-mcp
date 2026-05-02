"""Abstract transport for the bridge wire protocol.

The bridge speaks newline-delimited JSON-RPC 2.0. Concrete transports must
provide line-oriented read/write semantics and a connect/close lifecycle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Transport(ABC):
    """Newline-delimited byte stream."""

    @abstractmethod
    def connect(self, timeout: float | None = None) -> None:
        """Open the underlying connection. Raises ConnectionError on failure."""

    @abstractmethod
    def send_line(self, payload: bytes) -> None:
        """Write a single line (caller does not include trailing newline)."""

    @abstractmethod
    def recv_line(self, timeout: float | None = None) -> bytes:
        """Read a single line. Raises ConnectionError or TimeoutError."""

    @abstractmethod
    def close(self) -> None:
        """Idempotent close."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable transport identifier (used in logs/errors)."""

    def is_alive(self) -> bool:
        """Non-destructive liveness probe.

        Returns True when the transport is currently connected and the
        underlying socket / pipe is still open. Concrete subclasses should
        override this with a peek-style check (``MSG_PEEK`` on sockets,
        ``PeekNamedPipe`` on Windows). The default implementation is
        conservative — it returns False so callers never assume liveness.

        This is informational only; it must NOT consume bytes from the
        stream. Callers use it to decide whether a reconnect attempt is
        warranted before paying the cost of an actual JSON-RPC ping.
        """
        return False
