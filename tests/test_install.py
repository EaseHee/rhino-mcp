"""Tests for the ``rhino-mcp install`` / ``uninstall`` sub-commands."""

from __future__ import annotations

import json
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

from rhino_mcp import __version__
from rhino_mcp import install as install_mod
from rhino_mcp.install import (
    CLIENTS,
    antigravity_config_path,
    build_server_entry,
    claude_code_config_path,
    codex_config_path,
    default_config_path,
    load_config,
    merge_entry,
    resolve_launcher,
    toml_string,
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


def test_resolve_launcher_explicit_uvx_uses_absolute_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: f"/opt/bin/{name}")
    cmd, args = resolve_launcher("uvx")
    assert cmd == "/opt/bin/uvx"
    assert args == ["--from", f"rhino3dm-mcp>={__version__}", "rhino3dm-mcp"]


def test_resolve_launcher_uvx_found_in_fallback_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # GUI PATH misses ~/.local/bin; the absolute path must still be written.
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    uvx = bin_dir / "uvx"
    uvx.write_text("#!/bin/sh\n", encoding="utf-8")
    uvx.chmod(0o755)
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(install_mod, "_LAUNCHER_FALLBACK_DIRS", (str(bin_dir),))
    cmd, _ = resolve_launcher("uvx")
    assert cmd == str(uvx)


def test_resolve_launcher_explicit_uvx_bare_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(install_mod, "_LAUNCHER_FALLBACK_DIRS", (str(tmp_path),))
    cmd, args = resolve_launcher("uvx")
    assert cmd == "uvx"
    assert args == ["--from", f"rhino3dm-mcp>={__version__}", "rhino3dm-mcp"]


def test_auto_launcher_skips_uvx_when_pypi_lacks_this_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Before a release reaches PyPI, `uvx rhino3dm-mcp` would start an older server.
    probes: list[list[str]] = []

    def _run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        probes.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "No solution found when resolving tool dependencies")

    monkeypatch.setattr(install_mod, "find_launcher_binary", lambda name: "/opt/bin/uvx" if name == "uvx" else None)
    monkeypatch.setattr(install_mod.subprocess, "run", _run)
    monkeypatch.setattr(install_mod.sys, "executable", str(tmp_path / "python3"))

    cmd, args = resolve_launcher()

    assert probes == [["/opt/bin/uvx", "--from", f"rhino3dm-mcp>={__version__}", "rhino3dm-mcp", "--version"]]
    assert (cmd, args) == (str(tmp_path / "python3"), ["-m", "rhino_mcp.server"])


def test_auto_launcher_uses_uvx_when_pypi_serves_this_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install_mod, "find_launcher_binary", lambda name: "/opt/bin/uvx" if name == "uvx" else None)
    monkeypatch.setattr(
        install_mod.subprocess,
        "run",
        lambda cmd, **_kw: subprocess.CompletedProcess(cmd, 0, f"rhino-mcp {__version__}\n", ""),
    )
    assert resolve_launcher() == ("/opt/bin/uvx", ["--from", f"rhino3dm-mcp>={__version__}", "rhino3dm-mcp"])


def test_auto_launcher_prefers_own_script_over_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_bin = tmp_path / "env" / "bin"
    env_bin.mkdir(parents=True)
    own = env_bin / "rhino-mcp"
    own.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(install_mod.sys, "executable", str(env_bin / "python3"))
    # A stale script elsewhere on PATH must not be written into client configs.
    monkeypatch.setattr(install_mod, "find_launcher_binary", lambda name: f"/stale/bin/{name}" if name == "rhino-mcp" else None)

    assert resolve_launcher() == (str(own), [])
    assert resolve_launcher("rhino-mcp") == (str(own), [])


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


# ---------------------------------------------------------------------------
# Multi-client support
# ---------------------------------------------------------------------------

# Captured before the autouse fixture stubs it out.
_REAL_FIND_EXECUTABLE = install_mod.find_executable

UVX_ENTRY = {
    "command": "uvx",
    "args": ["rhino3dm-mcp"],
    "env": {"RHINO_MCP_TRANSPORT": "stdio"},
}

CODEX_PRELUDE = """# my codex settings - keep me
model = "o3"

[mcp_servers.other]
command = "other-cmd"
args = ["--flag"]

# profile comment - keep me too
[profiles.fast]
model = "o4-mini"
"""


@pytest.fixture(autouse=True)
def _no_real_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never shell out to a real claude/codex CLI from tests."""

    def _boom(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(install_mod, "find_executable", lambda name: None)
    monkeypatch.setattr(install_mod, "run_subprocess", _boom)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every client path at an empty temporary home directory."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setenv("APPDATA", str(h / "AppData" / "Roaming"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(install_mod, "resolve_launcher", lambda prefer=None: ("uvx", ["rhino3dm-mcp"]))
    return h


def _paths(h: Path) -> dict[str, Path]:
    return {
        "claude-desktop": h / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        "claude-code": h / ".claude.json",
        "codex": h / ".codex" / "config.toml",
        "antigravity": h / ".gemini" / "antigravity" / "mcp_config.json",
    }


def _backups(path: Path) -> list[Path]:
    return list(path.parent.glob(path.name + ".bak.*"))


@pytest.mark.parametrize("plat", ["darwin", "win32", "linux"])
def test_client_paths_per_platform(home: Path, plat: str) -> None:
    assert claude_code_config_path(plat) == home / ".claude.json"
    assert codex_config_path(plat) == home / ".codex" / "config.toml"
    assert antigravity_config_path(plat) == home / ".gemini" / "antigravity" / "mcp_config.json"
    expected = {
        "darwin": home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        "win32": home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        "linux": home / ".config" / "Claude" / "claude_desktop_config.json",
    }[plat]
    assert default_config_path(plat) == expected


def test_codex_home_override(home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ch"))
    assert codex_config_path("linux") == tmp_path / "ch" / "config.toml"


def test_win32_uses_userprofile(home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "prof"))
    assert codex_config_path("win32") == tmp_path / "prof" / ".codex" / "config.toml"
    assert claude_code_config_path("win32") == tmp_path / "prof" / ".claude.json"
    assert antigravity_config_path("win32") == tmp_path / "prof" / ".gemini" / "antigravity" / "mcp_config.json"


def test_toml_string_escaping_round_trips() -> None:
    tricky = 'C:\\Program Files\\py "x"\n\ttab\x01'
    assert tomllib.loads(f"k = {toml_string(tricky)}")["k"] == tricky


def test_codex_install_preserves_comments_and_other_tables(home: Path) -> None:
    cfg = _paths(home)["codex"]
    cfg.parent.mkdir(parents=True)
    cfg.write_text(CODEX_PRELUDE, encoding="utf-8")

    assert server_main(["install", "--client", "codex", "--no-backup"]) == 0

    text = cfg.read_text(encoding="utf-8")
    assert text.startswith(CODEX_PRELUDE)
    assert "[mcp_servers.rhino-mcp]" in text
    assert "[mcp_servers.rhino-mcp.env]" in text
    data = tomllib.loads(text)
    assert data["mcp_servers"]["rhino-mcp"] == UVX_ENTRY
    assert data["mcp_servers"]["other"] == {"command": "other-cmd", "args": ["--flag"]}
    assert data["profiles"]["fast"] == {"model": "o4-mini"}


def test_codex_force_replaces_only_our_block(home: Path) -> None:
    cfg = _paths(home)["codex"]
    cfg.parent.mkdir(parents=True)
    head, rest = CODEX_PRELUDE.split("[mcp_servers.other]")
    rest = "[mcp_servers.other]" + rest
    cfg.write_text(
        head
        + '[mcp_servers.rhino-mcp]\ncommand = "old"\nargs = []\n\n'
        + '[mcp_servers.rhino-mcp.env]\nRHINO_MCP_FORCE_MODE = "bridge"\n\n'
        + rest,
        encoding="utf-8",
    )

    assert server_main(["install", "--client", "codex"]) == 1
    assert tomllib.loads(cfg.read_text(encoding="utf-8"))["mcp_servers"]["rhino-mcp"]["command"] == "old"

    assert server_main(["install", "--client", "codex", "--force", "--no-backup"]) == 0
    text = cfg.read_text(encoding="utf-8")
    # FORCE_MODE is installer-owned, so switching back to auto mode drops it.
    assert "RHINO_MCP_FORCE_MODE" not in text
    assert text.startswith(head + "[mcp_servers.rhino-mcp]\n")
    assert text.endswith("\n\n" + rest)
    data = tomllib.loads(text)
    assert data["mcp_servers"]["rhino-mcp"] == UVX_ENTRY
    assert data["mcp_servers"]["other"]["command"] == "other-cmd"


@pytest.mark.parametrize("client", sorted(CLIENTS))
def test_rerun_is_unchanged(home: Path, client: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert server_main(["install", "--client", client]) == 0
    path = _paths(home)[client]
    before = path.read_text(encoding="utf-8")
    capsys.readouterr()

    assert server_main(["install", "--client", client]) == 0
    assert "unchanged" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == before
    assert _backups(path) == []


def test_force_overwrite_json_writes_backup(home: Path) -> None:
    path = _paths(home)["antigravity"]
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"rhino-mcp": {"command": "old"}}}), encoding="utf-8")

    assert server_main(["install", "--client", "antigravity"]) == 1
    assert server_main(["install", "--client", "antigravity", "--force"]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"] == UVX_ENTRY
    assert len(_backups(path)) == 1


@pytest.mark.parametrize("client", sorted(CLIENTS))
def test_uninstall_leaves_other_servers(home: Path, client: str) -> None:
    path = _paths(home)[client]
    path.parent.mkdir(parents=True, exist_ok=True)
    if client == "codex":
        path.write_text(CODEX_PRELUDE, encoding="utf-8")
    else:
        path.write_text(json.dumps({"mcpServers": {"other": {"command": "y"}}, "keep": 1}), encoding="utf-8")
    original = path.read_text(encoding="utf-8")

    assert server_main(["install", "--client", client, "--no-backup"]) == 0
    assert server_main(["uninstall", "--client", client]) == 0

    if client == "codex":
        assert path.read_text(encoding="utf-8") == original
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"mcpServers": {"other": {"command": "y"}}, "keep": 1}
    assert len(_backups(path)) == 1

    # A second uninstall reports absent and leaves the file alone.
    assert server_main(["uninstall", "--client", client]) == 0
    assert len(_backups(path)) == 1


def test_uninstall_missing_files_are_absent(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert server_main(["uninstall", "--client", "all"]) == 0
    assert capsys.readouterr().out.count("absent") == 4
    assert not any(p.exists() for p in _paths(home).values())


def test_install_all_writes_four_targets(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert server_main(["install", "--client", "all"]) == 0
    paths = _paths(home)
    for client in ("claude-desktop", "antigravity"):
        assert json.loads(paths[client].read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"] == UVX_ENTRY
    assert json.loads(paths["claude-code"].read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"] == {
        "type": "stdio",
        **UVX_ENTRY,
    }
    assert tomllib.loads(paths["codex"].read_text(encoding="utf-8"))["mcp_servers"]["rhino-mcp"] == UVX_ENTRY
    out = capsys.readouterr().out
    assert out.count("added") == 4
    assert "Restart Claude Desktop, Claude Code, Codex, Antigravity" in out


def test_install_detected_only_targets_present_clients(home: Path) -> None:
    (home / ".codex").mkdir()
    (home / ".gemini" / "antigravity").mkdir(parents=True)

    assert server_main(["install", "--client", "detected"]) == 0
    paths = _paths(home)
    assert paths["codex"].exists()
    assert paths["antigravity"].exists()
    assert not paths["claude-desktop"].exists()
    assert not paths["claude-code"].exists()


def test_install_detected_with_nothing_present_fails(home: Path) -> None:
    assert server_main(["install", "--client", "detected"]) == 2
    assert not any(p.exists() for p in _paths(home).values())


def test_detected_via_cli_on_path(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install_mod, "find_executable", lambda name: "/fake/codex" if name == "codex" else None)
    assert CLIENTS["codex"].detected() is True
    assert CLIENTS["claude-code"].detected() is False


def test_list_clients_json(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert server_main(["install", "--client", "antigravity"]) == 0
    capsys.readouterr()

    assert server_main(["install", "--list-clients", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == set(CLIENTS)
    assert by_name["antigravity"]["installed"] is True
    assert by_name["antigravity"]["detected"] is True
    assert by_name["codex"] == {
        "name": "codex",
        "label": "Codex",
        "path": str(home / ".codex" / "config.toml"),
        "detected": False,
        "installed": False,
    }


def test_list_clients_human(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert server_main(["install", "--list-clients"]) == 0
    out = capsys.readouterr().out
    for name in CLIENTS:
        assert name in out


def test_claude_code_uses_cli_when_available(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(install_mod, "find_executable", lambda name: "/fake/claude" if name == "claude" else None)
    monkeypatch.setattr(install_mod, "run_subprocess", fake_run)
    cfg = home / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"rhino-mcp": {"command": "old"}}}), encoding="utf-8")

    assert server_main(["install", "--client", "claude-code"]) == 1
    assert calls == []

    assert server_main(["install", "--client", "claude-code", "--force"]) == 0
    assert calls[0] == ["/fake/claude", "mcp", "remove", "--scope", "user", "rhino-mcp"]
    assert calls[1][:6] == ["/fake/claude", "mcp", "add-json", "--scope", "user", "rhino-mcp"]
    assert json.loads(calls[1][6]) == {"type": "stdio", **UVX_ENTRY}
    # The CLI owns the file; the installer must not rewrite it itself.
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"] == {"command": "old"}
    # A safety backup is taken before the CLI mutates the file.
    assert len(_backups(cfg)) == 1

    calls.clear()
    assert server_main(["uninstall", "--client", "claude-code"]) == 0
    assert calls == [["/fake/claude", "mcp", "remove", "--scope", "user", "rhino-mcp"]]


def test_claude_code_cli_add_only_for_new_entry(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(install_mod, "find_executable", lambda name: "/fake/claude" if name == "claude" else None)
    monkeypatch.setattr(install_mod, "run_subprocess", fake_run)

    assert server_main(["install", "--client", "claude-code"]) == 0
    assert [c[2] for c in calls] == ["add-json"]
    assert not (home / ".claude.json").exists()


def test_claude_code_cli_failure_is_error(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install_mod, "find_executable", lambda name: "/fake/claude" if name == "claude" else None)
    monkeypatch.setattr(
        install_mod,
        "run_subprocess",
        lambda cmd: subprocess.CompletedProcess(cmd, 1, "", "boom: not logged in"),
    )
    assert server_main(["install", "--client", "claude-code"]) == 1


@pytest.mark.parametrize(
    "clients",
    [["--client", "codex", "--client", "antigravity"], ["--client", "all"], ["--client", "detected"]],
)
def test_config_path_requires_single_concrete_client(home: Path, tmp_path: Path, clients: list[str]) -> None:
    cfg = tmp_path / "x.json"
    assert server_main(["install", *clients, "--config-path", str(cfg)]) == 2
    assert server_main(["uninstall", *clients, "--config-path", str(cfg)]) == 2
    assert not cfg.exists()


def test_config_path_with_codex_client(home: Path, tmp_path: Path) -> None:
    cfg = tmp_path / "custom.toml"
    assert server_main(["install", "--client", "codex", "--config-path", str(cfg)]) == 0
    assert tomllib.loads(cfg.read_text(encoding="utf-8"))["mcp_servers"]["rhino-mcp"] == UVX_ENTRY
    assert not _paths(home)["codex"].exists()


def test_invalid_toml_exits_2(home: Path) -> None:
    cfg = _paths(home)["codex"]
    cfg.parent.mkdir(parents=True)
    cfg.write_text("[[[ not toml", encoding="utf-8")
    assert server_main(["install", "--client", "codex"]) == 2
    assert cfg.read_text(encoding="utf-8") == "[[[ not toml"


def test_dry_run_codex_prints_toml(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert server_main(["install", "--client", "codex", "--dry-run"]) == 0
    assert tomllib.loads(capsys.readouterr().out)["mcp_servers"]["rhino-mcp"] == UVX_ENTRY
    assert not _paths(home)["codex"].exists()


# ---------------------------------------------------------------------------
# Follow-up regressions
# ---------------------------------------------------------------------------

BRACKET_TABLE = '[projects."/tmp/a]b"]\ntrust_level = "trusted"\n'


@pytest.mark.parametrize("argv", [["install", "--force"], ["uninstall"]])
def test_codex_quoted_header_with_bracket_survives(home: Path, argv: list[str]) -> None:
    cfg = _paths(home)["codex"]
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '[mcp_servers.rhino-mcp]\ncommand = "old"\nargs = []\n\n' + BRACKET_TABLE,
        encoding="utf-8",
    )

    assert server_main([*argv, "--client", "codex", "--no-backup"]) == 0

    text = cfg.read_text(encoding="utf-8")
    assert text.endswith(BRACKET_TABLE)
    assert tomllib.loads(text)["projects"] == {"/tmp/a]b": {"trust_level": "trusted"}}


def test_parse_table_header_forms() -> None:
    assert install_mod.parse_table_header('[projects."/tmp/a]b"]  # c') == ["projects", "/tmp/a]b"]
    assert install_mod.parse_table_header("[[arr . 'x]y']]") == ["arr", "x]y"]
    assert install_mod.parse_table_header('key = "[not]"') is None
    assert install_mod.parse_table_header("[a] trailing") is None


def _scripted_run(
    codes: list[int], calls: list[list[str]]
) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, codes[len(calls) - 1], "", "add failed")

    return fake_run


@pytest.mark.parametrize(
    ("codes", "detail"),
    [([0, 1, 0], "previous entry restored"), ([0, 1, 1], "previous entry removed and restore failed")],
)
def test_claude_code_cli_restores_previous_entry_when_add_fails(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    codes: list[int],
    detail: str,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(install_mod, "find_executable", lambda name: "/fake/claude" if name == "claude" else None)
    monkeypatch.setattr(install_mod, "run_subprocess", _scripted_run(codes, calls))
    cfg = home / ".claude.json"
    old = {"type": "stdio", "command": "old", "args": [], "env": {}}
    cfg.write_text(json.dumps({"mcpServers": {"rhino-mcp": old}}), encoding="utf-8")

    assert server_main(["install", "--client", "claude-code", "--force"]) == 1

    assert [c[2] for c in calls] == ["remove", "add-json", "add-json"]
    assert json.loads(calls[2][6]) == old
    assert detail in capsys.readouterr().out
    assert len(_backups(cfg)) == 1


def test_force_merge_keeps_user_keys_json(home: Path) -> None:
    path = _paths(home)["claude-desktop"]
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"rhino-mcp": {
        "command": "old",
        "args": [],
        "env": {
            "RHINO_MCP_TRANSPORT": "http",
            "RHINO_MCP_FORCE_MODE": "bridge",
            "RHINO_MCP_TOOLSETS": "core,bim",
            "RHINO_MCP_LOG_LEVEL": "DEBUG",
        },
        "disabled": False,
    }}}), encoding="utf-8")

    assert server_main(["install", "--force", "--no-backup"]) == 0
    entry = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["rhino-mcp"]
    assert entry == {
        "command": "uvx",
        "args": ["rhino3dm-mcp"],
        "env": {
            "RHINO_MCP_TOOLSETS": "core,bim",
            "RHINO_MCP_LOG_LEVEL": "DEBUG",
            "RHINO_MCP_TRANSPORT": "stdio",
        },
        "disabled": False,
    }
    # User keys alone do not count as a conflicting entry.
    assert server_main(["install"]) == 0


def test_force_merge_keeps_user_keys_toml(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _paths(home)["codex"]
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '[mcp_servers.rhino-mcp]\ncommand = "old"\nargs = []\n'
        "startup_timeout_sec = 30\ntool_timeout_sec = 60.5\nenabled = true\n\n"
        '[mcp_servers.rhino-mcp.env]\nRHINO_MCP_LOG_LEVEL = "DEBUG"\nRHINO_MCP_FORCE_MODE = "bridge"\n',
        encoding="utf-8",
    )

    assert server_main(["install", "--client", "codex", "--force", "--mode", "standalone", "--no-backup"]) == 0
    entry = tomllib.loads(cfg.read_text(encoding="utf-8"))["mcp_servers"]["rhino-mcp"]
    assert entry == {
        "command": "uvx",
        "args": ["rhino3dm-mcp"],
        "startup_timeout_sec": 30,
        "tool_timeout_sec": 60.5,
        "enabled": True,
        "env": {
            "RHINO_MCP_LOG_LEVEL": "DEBUG",
            "RHINO_MCP_TRANSPORT": "stdio",
            "RHINO_MCP_FORCE_MODE": "standalone",
        },
    }
    capsys.readouterr()
    assert server_main(["install", "--client", "codex", "--mode", "standalone"]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_cli_detection_probes_gui_fallback_dirs(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bindir = home / ".local" / "bin"
    bindir.mkdir(parents=True)
    claude = bindir / "claude"
    claude.write_text("#!/bin/sh\n", encoding="utf-8")
    claude.chmod(0o755)
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(install_mod, "_LAUNCHER_FALLBACK_DIRS", (str(bindir),))
    monkeypatch.setattr(install_mod, "find_executable", _REAL_FIND_EXECUTABLE)

    assert _REAL_FIND_EXECUTABLE("claude") == str(claude)
    assert CLIENTS["claude-code"].detected() is True
    assert CLIENTS["codex"].detected() is False


def test_list_clients_reports_broken_config(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _paths(home)["antigravity"]
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    assert server_main(["install", "--list-clients", "--json"]) == 0
    row = {r["name"]: r for r in json.loads(capsys.readouterr().out)}["antigravity"]
    assert row["installed"] is False
    assert "not valid JSON" in row["error"]

    assert server_main(["install", "--list-clients"]) == 0
    line = next(ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("antigravity"))
    assert " error " in line


def test_backups_in_same_second_do_not_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install_mod.time, "strftime", lambda _fmt: "20260101-000000")
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"v": 1}', encoding="utf-8")
    first = write_config(cfg, {"v": 2}, backup=True)
    second = write_config(cfg, {"v": 3}, backup=True)
    assert first is not None and second is not None and first != second
    assert json.loads(first.read_text(encoding="utf-8")) == {"v": 1}
    assert json.loads(second.read_text(encoding="utf-8")) == {"v": 2}


def test_codex_entry_with_datetime_survives_force(home: Path) -> None:
    import datetime as dt

    cfg = _paths(home)["codex"]
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '[mcp_servers.rhino-mcp]\ncommand = "old"\nargs = []\nadded = 2024-01-01T00:00:00Z\n',
        encoding="utf-8",
    )
    rc = server_main(
        ["install", "--client", "codex", "--client", "claude-desktop", "--force", "--no-backup"]
    )
    assert rc == 0
    entry = tomllib.loads(cfg.read_text(encoding="utf-8"))["mcp_servers"]["rhino-mcp"]
    assert entry["added"] == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert entry["command"] == "uvx"
    assert _paths(home)["claude-desktop"].exists()
