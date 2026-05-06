"""Utility-layer tests (errors, logging, capability registry, document registry)."""

from __future__ import annotations

import logging

import pytest

from rhino_mcp.document import registry
from rhino_mcp.utils.error_handling import (
    ErrorCategory,
    connection_error,
    gh_component_missing,
    not_found_error,
    parameter_error,
    unsupported_in_standalone,
)
from rhino_mcp.utils.logging import configure, get_logger
from rhino_mcp.utils.registry import Mode, is_compatible, register_tools
from rhino_mcp.utils.serialization import gid_str


def test_tool_error_categories_have_actionable_hints() -> None:
    err = parameter_error("radius", "must be positive", "any value > 0")
    assert err.category is ErrorCategory.PARAMETER
    assert "radius" in err.hint and ">" in err.hint
    payload = err.to_dict()
    assert payload["error"]["category"] == "parameter"

    nf = not_found_error("file", "/x.3dm")
    assert nf.category is ErrorCategory.NOT_FOUND

    conn = connection_error("transport down")
    assert "rhino-mcp" in conn.hint

    unsupp = unsupported_in_standalone("rhino_loft")
    assert unsupp.category is ErrorCategory.UNSUPPORTED

    gh = gh_component_missing("Voronoi", suggestion="Voronoi 2D")
    assert "Voronoi 2D" in gh.hint


def test_logging_singleton(caplog: pytest.LogCaptureFixture) -> None:
    configure("DEBUG")
    log = get_logger("server")
    log.info("hello")
    # Logger name is normalised to rhino_mcp.<module>.
    assert log.name == "rhino_mcp.server"
    assert log.level <= logging.INFO


def test_register_tools_filters_by_capability() -> None:
    calls: list[Mode] = []

    def reg_both(_mcp, _mode): calls.append(Mode.BOTH)

    def reg_bridge(_mcp, _mode): calls.append(Mode.BRIDGE)

    applied = register_tools(
        object(),
        Mode.STANDALONE,
        [(Mode.BOTH, reg_both), (Mode.BRIDGE, reg_bridge)],
    )
    assert applied == 1
    assert calls == [Mode.BOTH]

    calls.clear()
    applied = register_tools(
        object(),
        Mode.BRIDGE,
        [(Mode.BOTH, reg_both), (Mode.BRIDGE, reg_bridge)],
    )
    assert applied == 2
    assert set(calls) == {Mode.BOTH, Mode.BRIDGE}


def test_is_compatible_truth_table() -> None:
    truth = [
        (Mode.STANDALONE, Mode.STANDALONE, True),
        (Mode.STANDALONE, Mode.BRIDGE, False),
        (Mode.BRIDGE, Mode.STANDALONE, False),
        (Mode.BRIDGE, Mode.BRIDGE, True),
        (Mode.BOTH, Mode.STANDALONE, True),
        (Mode.BOTH, Mode.BRIDGE, True),
    ]
    for cap, runtime, expected in truth:
        assert is_compatible(cap, runtime) is expected, (cap, runtime, expected)


def test_document_registry_lifecycle() -> None:
    reg = registry()
    h1 = reg.get_or_create("alpha")
    h2 = reg.get_or_create("alpha")
    assert h1 is h2
    assert "alpha" in reg.list_ids()


def test_gid_str_normalises() -> None:
    import uuid

    u = uuid.uuid4()
    assert gid_str(u) == str(u)


def _capture_log(logger_name: str):
    """Context manager: temporarily attach a StringIO handler to a logger."""
    import contextlib
    import io

    @contextlib.contextmanager
    def _ctx():
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        log = logging.getLogger(logger_name)
        log.addHandler(handler)
        try:
            yield buf
        finally:
            log.removeHandler(handler)

    return _ctx()


def test_register_tools_logs_warning_when_no_match() -> None:
    """register_tools with no matching modules should emit a WARNING."""
    with _capture_log("rhino_mcp") as buf:
        applied = register_tools(object(), Mode.STANDALONE, [(Mode.BRIDGE, lambda _m, _r: None)])
    assert applied == 0
    assert "No tool modules matched" in buf.getvalue()


def test_context_set_runtime_duplicate_logs_warning() -> None:
    """set_runtime() called twice outside test mode should log a warning."""
    from rhino_mcp.tools import context as ctx

    ctx.disable_testing()
    try:
        ctx.set_runtime(Mode.STANDALONE, None)
        with _capture_log("rhino_mcp") as buf:
            ctx.set_runtime(Mode.BRIDGE, None)
        assert "called twice" in buf.getvalue()
    finally:
        ctx.enable_testing()
        ctx.set_runtime(Mode.STANDALONE, None)


def test_context_runtime_raises_when_unset() -> None:
    """runtime() without set_runtime() raises RuntimeError outside test mode."""
    from rhino_mcp.tools import context as ctx

    ctx.disable_testing()
    ctx.reset()
    try:
        with pytest.raises(RuntimeError, match="set_runtime"):
            ctx.runtime()
    finally:
        ctx.enable_testing()
        ctx.set_runtime(Mode.STANDALONE, None)


def test_bridge_client_is_healthy_and_ping(monkeypatch) -> None:
    """is_healthy reflects _connected; ping() returns False when not connected."""
    from rhino_mcp.bridge.rhino_connection import BridgeClient
    from rhino_mcp.bridge.transport_base import Transport

    class _NullTransport(Transport):
        name = "null://test"
        def connect(self, timeout=None): pass
        def send_line(self, payload): pass
        def recv_line(self, timeout=None): return b""
        def close(self): pass

    client = BridgeClient(_NullTransport(), timeout=1.0)
    assert not client.is_healthy
    assert not client.ping()

    client._connected = True
    assert client.is_healthy

    client.close()
    assert not client.is_healthy


def test_bridge_client_reconnect_failure(monkeypatch) -> None:
    """reconnect() returns False when transport.connect() raises."""
    from rhino_mcp.bridge.rhino_connection import BridgeClient
    from rhino_mcp.bridge.transport_base import Transport

    class _FailTransport(Transport):
        name = "fail://test"
        def connect(self, timeout=None): raise ConnectionError("refused")
        def send_line(self, payload): pass
        def recv_line(self, timeout=None): return b""
        def close(self): pass

    client = BridgeClient(_FailTransport(), timeout=1.0)
    client._connected = True
    result = client.reconnect()
    assert result is False
    assert not client._connected


# Tool-helper utilities (pagination, MAX_OBJECT_IDS).
from rhino_mcp.tools._helpers import (  # noqa: E402
    DEFAULT_PAGE_LIMIT,
    MAX_OBJECT_IDS,
    MAX_PAGE_LIMIT,
    paginate,
)


def test_paginate_returns_first_page_and_next_cursor() -> None:
    rows = list(range(120))
    page, nxt = paginate(rows, cursor=0, limit=50)
    assert page == list(range(50))
    assert nxt == 50


def test_paginate_returns_none_cursor_when_exhausted() -> None:
    rows = list(range(10))
    page, nxt = paginate(rows, cursor=5, limit=50)
    assert page == list(range(5, 10))
    assert nxt is None


def test_paginate_clamps_limit_above_max() -> None:
    rows = list(range(MAX_PAGE_LIMIT + 50))
    page, nxt = paginate(rows, cursor=0, limit=10_000)
    assert len(page) == MAX_PAGE_LIMIT
    assert nxt == MAX_PAGE_LIMIT


def test_paginate_clamps_cursor_above_length() -> None:
    rows = list(range(10))
    page, nxt = paginate(rows, cursor=999, limit=10)
    assert page == []
    assert nxt is None


def test_paginate_default_limit_matches_constant() -> None:
    rows = list(range(DEFAULT_PAGE_LIMIT * 2))
    page, _ = paginate(rows)
    assert len(page) == DEFAULT_PAGE_LIMIT


def test_max_object_ids_constant_is_positive() -> None:
    assert MAX_OBJECT_IDS > 0
