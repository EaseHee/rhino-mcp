"""CLI / entry-point tests."""

from __future__ import annotations

import pytest

from rhino_mcp.transport import fastmcp_transport_arg, resolve_transport


def test_resolve_transport_default() -> None:
    assert resolve_transport(None) == "stdio"
    assert resolve_transport("stdio") == "stdio"
    assert resolve_transport("http") == "http"
    assert resolve_transport("streamable-http") == "http"


def test_resolve_transport_invalid() -> None:
    with pytest.raises(ValueError):
        resolve_transport("ws")


def test_fastmcp_transport_arg() -> None:
    assert fastmcp_transport_arg("stdio") == "stdio"
    assert fastmcp_transport_arg("http") == "streamable-http"


def test_main_version_exits_zero(capsys, monkeypatch) -> None:
    from rhino_mcp.server import main

    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr()
    assert "rhino-mcp" in (out.out + out.err)


def test_main_import_error_returns_2(monkeypatch) -> None:
    """build_server raising ImportError → exit code 2."""
    from rhino_mcp.server import main

    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")

    def _raise_import(*_, **__):
        raise ImportError("missing-pkg")

    monkeypatch.setattr("rhino_mcp.server.build_server", _raise_import)
    assert main([]) == 2


def test_main_connection_error_returns_3(monkeypatch) -> None:
    """build_server raising ConnectionError → exit code 3."""
    from rhino_mcp.server import main

    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")

    def _raise_conn(*_, **__):
        raise ConnectionError("no bridge")

    monkeypatch.setattr("rhino_mcp.server.build_server", _raise_conn)
    assert main([]) == 3


def test_main_generic_error_returns_1(monkeypatch) -> None:
    """build_server raising unexpected error → exit code 1."""
    from rhino_mcp.server import main

    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")

    def _raise(*_, **__):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("rhino_mcp.server.build_server", _raise)
    assert main([]) == 1


def test_main_keyboard_interrupt_returns_0(monkeypatch) -> None:
    """KeyboardInterrupt during mcp.run() → clean exit, code 0."""
    from unittest.mock import MagicMock

    from rhino_mcp.server import main

    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")

    mock_mcp = MagicMock()
    mock_mcp.run.side_effect = KeyboardInterrupt
    mock_mcp.settings.host = "127.0.0.1"
    mock_mcp.settings.port = 8765

    monkeypatch.setattr("rhino_mcp.server.build_server", lambda *_, **__: (mock_mcp, 5))
    assert main([]) == 0


def test_main_connector_flags_configure_settings(monkeypatch) -> None:
    """--allow-external and --stateless update FastMCP settings before run()."""
    from unittest.mock import MagicMock

    from mcp.server.transport_security import TransportSecuritySettings

    from rhino_mcp.server import main

    monkeypatch.setenv("RHINO_MCP_FORCE_MODE", "standalone")

    ts = TransportSecuritySettings()
    mock_settings = MagicMock()
    mock_settings.transport_security = ts
    mock_settings.host = "0.0.0.0"
    mock_settings.port = 8765
    mock_settings.stateless_http = False

    mock_mcp = MagicMock()
    mock_mcp.settings = mock_settings
    mock_mcp.run.side_effect = KeyboardInterrupt

    monkeypatch.setattr("rhino_mcp.server.build_server", lambda *_, **__: (mock_mcp, 5))
    result = main(["--transport", "http", "--allow-external", "--stateless"])
    assert result == 0
    assert ts.enable_dns_rebinding_protection is False
    assert ts.allowed_hosts == ["*"]
    assert ts.allowed_origins == ["*"]
    assert mock_settings.stateless_http is True
