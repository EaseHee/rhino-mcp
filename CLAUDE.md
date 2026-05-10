# rhino-mcp

MCP server connecting Claude to McNeel Rhino 8 and Grasshopper.

## Architecture

- **Standalone**: `rhino3dm` (headless Python lib) for `.3dm` I/O. ~234 tools.
- **Bridge**: C# plugin `rhino_plugin/csharp/rhino-mcp.rhp` over JSON-RPC 2.0. ~235 tools.
- Mode auto-detected at startup (`detect_mode()`); override via `RHINO_MCP_FORCE_MODE`.

## Project layout (top level)

- `src/rhino_mcp/` — Python package (server, tools, bridge transports, prompts, models, utils, data).
- `rhino_plugin/csharp/` — C# bridge plugin (`Plugin.cs`, `BridgeServer.cs`, `CommandDispatcher.cs`, `Handlers/*.cs`, `manifest.yml`).
- `tests/` — pytest (~262 tests).
- `examples/` — runnable demo scripts (architectural massing, schedule, sun study, etc.).
- `docs/{en,ko}/` — capabilities / configuration / installation / troubleshooting / tools-reference / grasshopper-guide.
- `.github/workflows/` — CI + release pipelines.
- `.claude/` — agents, skills, commands, rules, settings.

## Development

```bash
uv sync
uv pip install -e '.[dev]'
uv run pytest tests/ -v                    # all tests
uv run ruff check src/ tests/              # lint
uv run mypy src/rhino_mcp                  # type check
dotnet build rhino_plugin/csharp -c Release
```

## Conventions

- Tool first argument: `args: _InputModel` (Pydantic BaseModel).
- `doc_id` defaults to `"active"`.
- Shared logic lives in `tools/_helpers.py`.
- `Mode` enum: `STANDALONE` / `BRIDGE` / `BOTH`.
- **Commit messages: English title + English body**, Conventional Commits, no Co-Authored-By.
- **Code comments: English only.**
- **Korean prose** (chat replies, `*.ko.md`, `docs/ko/**`, CHANGELOG entries) uses **noun-form endings, no honorifics** (`-함`, `-임`, or noun direct termination; never `입니다 / 합니다 / 하세요`).

## Procedure docs (lazy-loaded under `.claude/rules/`)

- Adding a new tool — `.claude/rules/adding-tool.md`.
- C# handler authoring + RhinoCommon trap list — `.claude/rules/csharp-handler.md`.
- Korean writing style — `.claude/rules/korean-style.md`.

## Subagents (`.claude/agents/`)

- `rhino3dm-api-checker` — verify Python-side rhino3dm signatures before use.
- `csharp-rhinocommon-checker` — run `dotnet build` + decode RhinoCommon errors.
- `release-coordinator` — sync version, tool counts, test counts across CHANGELOG / README / docs / commit-message.

## Slash commands (`.claude/commands/`)

- `/release-v [next_version]` — drive the release-coordinator.
- `/validate-bridge` — bridge health check ladder.
- `/sync-tool-docs` — refresh `docs/{en,ko}/capabilities.md` from live registrations.

## Key environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RHINO_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `RHINO_MCP_FORCE_MODE` | auto | `standalone` or `bridge` |
| `RHINO_MCP_BRIDGE_OPTIONAL` | `0` | `1` = fall back to standalone if bridge unreachable |
| `RHINO_MCP_BRIDGE_TIMEOUT` | `5` | Bridge auto-detect ping timeout (seconds) |
| `RHINO_MCP_RECONNECT_RETRIES` | `3` | Reconnect attempts after transport failure |
| `RHINO_MCP_REDETECT_COOLDOWN` | `5` | Min seconds between lazy promotion attempts |
| `RHINO_MCP_KEEPALIVE_IDLE` | `20` | TCP keepalive idle (seconds) |
| `RHINO_MCP_KEEPALIVE_INTERVAL` | `10` | TCP keepalive probe interval (seconds) |
| `RHINO_MCP_HEARTBEAT_INTERVAL` | `10` | Server-side heartbeat notification interval during long-running handlers |
| `RHINO_MCP_ALLOW_MODAL_COMMAND` | _(off)_ | `1` disables `rs.Command(_Move/...)` circuit breaker — debugging only |
| `RHINO_HOST` | `localhost` | Bridge TCP host |
| `RHINO_PORT` | `4242` | Bridge TCP port |
| `RHINO_MCP_LOG_LEVEL` | `INFO` | Logging level |

Full reference — `docs/en/configuration.md` (or `docs/ko/configuration.md`).
