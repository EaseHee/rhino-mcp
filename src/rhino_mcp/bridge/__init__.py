"""Bridge layer.

* ``rhino_connection`` — top-level mode detection and JSON-RPC client wrapper.
* ``transport_base`` — abstract transport (send_line/recv_line).
* ``named_pipe`` / ``unix_socket`` / ``tcp_socket`` — concrete transports.
"""

from rhino_mcp.bridge.rhino_connection import BridgeClient, Mode, detect_mode

__all__ = ["BridgeClient", "Mode", "detect_mode"]
