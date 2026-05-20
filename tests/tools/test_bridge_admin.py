"""Unit tests for tools/bridge_admin.py and bridge/discovery.py."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rhino_mcp.bridge import discovery
from tests.conftest import call_tool


def _write_announcement(
    dir_: Path,
    *,
    pid: int,
    port: int,
    doc_path: str = "/tmp/example.3dm",
    doc_title: str = "example.3dm",
) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": pid,
        "host": "127.0.0.1",
        "port": port,
        "doc_path": doc_path,
        "doc_title": doc_title,
        "rhino_version": "8.10.0",
        "protocol_version": "1.2",
        "started_at": "2026-05-16T09:00:00Z",
    }
    path = dir_ / f"{pid}-{port}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def listener_tmpdir(tmp_path, monkeypatch):
    monkeypatch.setenv("RHINO_MCP_LISTENER_DIR", str(tmp_path))
    return tmp_path


def test_listener_dir_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RHINO_MCP_LISTENER_DIR", str(tmp_path))
    assert discovery.listener_dir() == tmp_path


def test_list_rhino_instances_empty_when_dir_missing(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("RHINO_MCP_LISTENER_DIR", str(missing))
    assert discovery.list_rhino_instances() == []


def test_list_rhino_instances_reads_announcements(listener_tmpdir):
    # Use this test's own PID so _pid_alive returns True without a TCP probe success.
    _write_announcement(listener_tmpdir, pid=os.getpid(), port=49991)
    instances = discovery.list_rhino_instances(probe_timeout=0.05)
    assert len(instances) == 1
    inst = instances[0]
    assert inst.pid == os.getpid()
    assert inst.port == 49991
    # No listener is bound to that port, so alive must be False even though the PID is alive.
    assert inst.alive is False


def test_list_rhino_instances_cleans_stale_pid(listener_tmpdir):
    # PID 1 is init on POSIX (always alive); use a likely-dead high pid instead.
    stale_pid = 999_999_999
    path = _write_announcement(listener_tmpdir, pid=stale_pid, port=49992)
    instances = discovery.list_rhino_instances(stale_cleanup=True, probe_timeout=0.05)
    # Stale entry removed and not returned.
    assert all(i.pid != stale_pid for i in instances)
    assert not path.exists()


def test_bridge_list_instances_tool(server_standalone, listener_tmpdir):
    _mcp, tools = server_standalone
    _write_announcement(listener_tmpdir, pid=os.getpid(), port=49993)
    result = call_tool(
        tools,
        "rhino_bridge_list_instances",
        {"stale_cleanup": False, "probe_timeout": 0.05},
    )
    structured = result[1] if isinstance(result, tuple) else result
    assert structured["summary"]["count"] >= 1
    assert structured["row_count"] == len(structured["rows"])


def test_bridge_select_instance_requires_selector(server_standalone, listener_tmpdir):
    _mcp, tools = server_standalone
    _write_announcement(listener_tmpdir, pid=os.getpid(), port=49994)
    with pytest.raises(Exception, match=r"(?i)selector"):
        call_tool(tools, "rhino_bridge_select_instance", {})


def test_bridge_select_instance_no_match_raises(server_standalone, listener_tmpdir):
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r"(?i)selector"):
        call_tool(tools, "rhino_bridge_select_instance", {"port": 1})
