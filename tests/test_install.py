"""Tests for the ``rhino-mcp install`` sub-command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rhino_mcp import install as install_mod
from rhino_mcp.install import (
    build_server_entry,
    default_config_path,
    load_config,
    merge_entry,
    resolve_launcher,
    write_config,
)
from rhino_mcp.server import main as server_main


def test_default_config_path_macos() -> None:
    p = default_config_path("darwin")
    assert p.parts[-3:] == ("Application Support", "Claude", "claude_desktop_config.json")


def test_default_config_path_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = default_config_path("win32")
    assert p == tmp_path / "Claude" / "claude_desktop_config.json"


def test_default_config_path_linux() -> None:
    p = default_config_path("linux")
    assert p.parts[-3:] == (".config", "Claude", "claude_desktop_config.json")


def test_load_config_missing_file(tmp_path: Path) -> None:
    assert load_config(tmp_path / "nope.json") == {}


def test_load_config_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text("", encoding="utf-8")
    assert load_config(p) == {}


def test_build_server_entry_auto_mode() -> None:
    e = build_server_entry(mode="auto", transport="stdio", command="uvx", args=["rhino3dm-mcp"])
    assert e == {
        "command": "uvx",
        "args": ["rhino3dm-mcp"],
        "env": {"RHINO_MCP_TRANSPORT": "stdio"},
    }


def test_build_server_entry_force_mode() -> None:
    e = build_server_entry(mode="bridge", transport="http", command="rhino-mcp", args=[])
    assert e["env"]["RHINO_MCP_FORCE_MODE"] == "bridge"
    assert e["env"]["RHINO_MCP_TRANSPORT"] == "http"


def test_build_server_entry_rejects_bad_mode() -> None:
    with pytest.raises(ValueError):
        build_server_entry(mode="nope", transport="stdio", command="uvx", args=[])


def test_resolve_launcher_explicit_python() -> None:
    cmd, args = resolve_launcher("python")
    assert "python" in cmd.lower() or cmd.endswith(("python", "python3"))
    assert args == ["-m", "rhino_mcp.server"]


def test_resolve_launcher_explicit_uvx() -> None:
    cmd, args = resolve_launcher("uvx")
    assert cmd == "uvx"
    assert args == ["rhino3dm-mcp"]


def test_merge_entry_adds_new() -> None:
    new, changed, action = merge_entry({}, "rhino-mcp", {"command": "uvx", "args": []}, overwrite=False)
    assert changed is True
    assert action == "added"
    assert new["mcpServers"]["rhino-mcp"] == {"command": "uvx", "args": []}


def test_merge_entry_unchanged_when_identical() -> None:
    cfg = {"mcpServers": {"rhino-mcp": {"command": "uvx", "args": ["x"]}}}
    _, changed, action = merge_entry(
        cfg, "rhino-mcp", {"command": "uvx", "args": ["x"]}, overwrite=False
    )
    assert changed is False
    assert action == "unchanged"


def test_merge_entry_blocks_overwrite_without_force() -> None:
    cfg = {"mcpServers": {"rhino-mcp": {"command": "old", "args": []}}}
    new, changed, action = merge_entry(
        cfg, "rhino-mcp", {"command": "new", "args": []}, overwrite=False
    )
    assert changed is False
    assert action == "exists"
    assert new["mcpServers"]["rhino-mcp"]["command"] == "old"


def test_merge_entry_overwrites_with_force() -> None:
    cfg = {"mcpServers": {"rhino-mcp": {"command": "old", "args": []}}}
    new, changed, action = merge_entry(
        cfg, "rhino-mcp", {"command": "new", "args": []}, overwrite=True
    )
    assert changed is True
    assert action == "updated"
    assert new["mcpServers"]["rhino-mcp"]["command"] == "new"


def test_merge_entry_preserves_other_servers() -> None:
    cfg = {"mcpServers": {"other": {"command": "y"}}}
    new, _, _ = merge_entry(cfg, "rhino-mcp", {"command": "uvx", "args": []}, overwrite=False)
    assert new["mcpServers"]["other"] == {"command": "y"}


def test_merge_entry_rejects_non_dict_servers() -> None:
    with pytest.raises(ValueError):
        merge_entry({"mcpServers": []}, "rhino-mcp", {"command": "x"}, overwrite=False)


def test_write_config_creates_backup(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    backup = write_config(p, {"mcpServers": {"rhino-mcp": {"command": "uvx"}}}, backup=True)
    assert backup is not None
    assert backup.exists()
    assert json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"]["command"] == "uvx"


def test_write_config_skips_backup_when_no_prior_file(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    backup = write_config(p, {"mcpServers": {}}, backup=True)
    assert backup is None
    assert p.exists()


def test_write_config_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "deeper" / "nested" / "cfg.json"
    write_config(p, {"mcpServers": {}}, backup=False)
    assert p.exists()


def test_install_cli_writes_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(install_mod, "resolve_launcher", lambda prefer=None: ("uvx", ["rhino3dm-mcp"]))

    rc = server_main(["install", "--config-path", str(cfg)])
    assert rc == 0

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["rhino-mcp"] == {
        "command": "uvx",
        "args": ["rhino3dm-mcp"],
        "env": {"RHINO_MCP_TRANSPORT": "stdio"},
    }


def test_install_cli_dry_run_does_not_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    rc = server_main([
        "install",
        "--config-path", str(cfg),
        "--launcher", "python",
        "--dry-run",
    ])
    assert rc == 0
    assert not cfg.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "rhino-mcp" in parsed["mcpServers"]


def test_install_cli_force_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"rhino-mcp": {"command": "old", "args": []}}}), encoding="utf-8")
    monkeypatch.setattr(install_mod, "resolve_launcher", lambda prefer=None: ("uvx", ["rhino3dm-mcp"]))

    # Without --force the call should refuse.
    rc = server_main(["install", "--config-path", str(cfg)])
    assert rc == 1
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"]["command"] == "old"

    # With --force it should rewrite.
    rc = server_main(["install", "--config-path", str(cfg), "--force"])
    assert rc == 0
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"]["command"] == "uvx"


def test_install_cli_rejects_invalid_json(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("not json", encoding="utf-8")
    rc = server_main(["install", "--config-path", str(cfg)])
    assert rc == 2


def test_install_cli_force_mode_writes_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(install_mod, "resolve_launcher", lambda prefer=None: ("uvx", ["rhino3dm-mcp"]))

    rc = server_main([
        "install",
        "--config-path", str(cfg),
        "--mode", "bridge",
        "--transport", "stdio",
    ])
    assert rc == 0
    env = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"]["env"]
    assert env == {"RHINO_MCP_TRANSPORT": "stdio", "RHINO_MCP_FORCE_MODE": "bridge"}
