# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project logo at `assets/rhino-logo.png` referenced from both READMEs;
  `pyproject.toml` sdist `include` now ships the `assets/` directory.
- MCP prompts package (`src/rhino_mcp/prompts/strategy.py`) with three
  guides: `general_strategy`, `rhinoscript_workflow`, `viewport_workflow`.
- `rhino_screenshot(as_base64=True)` returns the PNG bytes inline as
  `image_base64` for LLM visual verification.
- `rhino_object_select` filter matrix: `name_pattern`, `layer`, `color`,
  `object_type`, `user_text`, `deselect_first` — combined with AND.
- `rhino_list_objects` carries a `pagination` block
  (`total`, `offset`, `limit`, `returned`, `has_more`).
- Async tool variants for `rhino_list_objects`, `rhino_document_summary`,
  `rhino_layer_list` using `BridgeClient.async_call`.
- `Transport.is_alive()` non-destructive liveness probe with `MSG_PEEK`
  (TCP/Unix) and `PeekNamedPipe` (Windows).
- Reconnect backoff jitter: `RHINO_MCP_RECONNECT_BASE_DELAY`,
  `RHINO_MCP_RECONNECT_JITTER`.
- `tools/_helpers.bridge_call` / `bridge_call_async` wrappers emitting
  DEBUG-level input/output traces.
- 17 new tests (`test_prompts.py`, `test_query.py`,
  `test_select_filters.py`, three new bridge connection tests).
- Thread-safe runtime context with lock protection (`tools/context.py`)
- Bridge auto-reconnection with configurable retries (`RHINO_MCP_RECONNECT_RETRIES`)
- Bridge health check: `ping()`, `is_healthy`, `reconnect()` methods
- `ErrorCategory.TIMEOUT` for timeout-specific error handling
- Transport buffer clearing on connection failure (all 3 transports)
- Request ID mismatch detection (raises error instead of warning)
- Docker compose health check configuration
- CLAUDE.md project documentation
- CONTRIBUTING.md with tool creation guide
- 33 new tests: bridge edge cases, Grasshopper tools, display/surface tools

### Changed
- README.md / README.ko.md largely rewritten: launch-mode matrix,
  per-OS Claude Desktop config-file paths, Cursor IDE example,
  claude.ai remote-connector walkthrough, base64 screenshot /
  pagination / rich-select usage examples, four new env vars
  documented, troubleshooting expanded.
- All Korean comments and docstrings in `src/`, `tests/`, and the C#
  plugin replaced with English to match the project convention.
- Pydantic `Field(...)` descriptions filled in across every tool module
  so parameter help surfaces in MCP clients.
- Removed private FastMCP API access (`_tool_manager._tools`) from server.py
- `send_line` now wraps OSError as ConnectionError across all transports
- `recv_line` now distinguishes TimeoutError from ConnectionError
- `register_tools()` logs warning when zero tools match the runtime mode
- Startup errors now show user-friendly messages with distinct exit codes
- Shared helper functions (`find_layer_index`, `find_material_index`) in `_helpers.py`

### Fixed
- `query.py` used `File3dmObjectTable.Count` which the rhino3dm 8.x
  binding does not expose, raising `AttributeError` on every standalone
  `list_objects` / `document_summary` / `layer_list`. Now uses `len(...)`.
- C# `IOHandler.Screenshot` previously read `output_path` while the
  Python tool sent `path` — both keys are now accepted.
- Global `_RUNTIME` state race condition under concurrent access
- Silent fallback to STANDALONE mode masking configuration errors
- Stale `_connected` flag not updated on transport failure
- Partial buffer data persisting after connection loss

## [0.1.0] - 2025-04-25

### Added
- Initial release
- 51 standalone tools (rhino3dm) + 119 bridge tools (RhinoCommon + Grasshopper)
- Dual-mode architecture: standalone and bridge
- Three transport types: named pipes (Windows), Unix sockets (macOS/Linux), TCP
- FastMCP server with stdio and Streamable HTTP transports
- Docker support with docker-compose
- Bilingual documentation (English + Korean)
- 62 pytest tests with 70% coverage threshold
- 3 example scripts: basic modeling, Grasshopper workflow, parametric facade
