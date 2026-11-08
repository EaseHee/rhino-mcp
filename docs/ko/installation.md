# 설치(Installation)

## 사전 요구 사항(Prerequisites)

- Python 3.11 이상.
- (선택) McNeel Rhino 8 또는 Rhino 9 — **브리지(bridge) 모드**에서만 필요(RhinoCommon, viewport, render, Grasshopper).
- (선택) Docker — 컨테이너로 실행하려는 경우.

## 서버 설치

### `uv` 사용(권장)

```bash
uv tool install rhino-mcp
```

git clone본에서 개발 실행:

```bash
git clone https://github.com/easehee/rhino-mcp.git
cd rhino-mcp
uv sync
uv run rhino-mcp --help
```

### `pip` 사용

```bash
pip install rhino3dm-mcp
rhino-mcp --version
```

Windows 옵션 extra(pywin32)는 v0.4 이전 named pipe 브리지 전용. 현재 플러그인은 TCP 로 수신:

```bash
pip install 'rhino3dm-mcp[windows]'
```

`rhino_bridge_list_instances`(다중 Rhino 발견)는 extra 불필요.

`rhino3dm` 최소 버전 8.35. macOS 휠은 macOS 14 이상 필요.

## MCP 클라이언트에 서버 등록

`rhino-mcp install`: 하나 이상의 MCP 클라이언트 설정에 `rhino-mcp` 항목 기록(기본 대상 Claude Desktop).

```bash
rhino-mcp install                          # Claude Desktop
rhino-mcp install --client claude-code     # Claude Code (user scope)
rhino-mcp install --client codex --client antigravity   # 반복 지정 가능
rhino-mcp install --client detected        # 이 머신에서 감지된 모든 클라이언트
rhino-mcp install --client all             # 지원 클라이언트 전체
rhino-mcp install --list-clients [--json]  # 감지 / 설치 상태
rhino-mcp install --dry-run                # 파일 변경 없이 미리보기
rhino-mcp uninstall --client all           # rhino-mcp 항목만 제거
```

| 클라이언트 | 대상 |
|-----------|------|
| `claude-desktop` | `claude_desktop_config.json` (변경 없음) |
| `claude-code` | `claude` CLI 존재 시 `claude mcp add-json --scope user`, 없으면 `~/.claude.json` 의 `mcpServers` (`CLAUDE_CONFIG_DIR` 존중) |
| `codex` | `$CODEX_HOME/config.toml` 또는 `~/.codex/config.toml` 의 `[mcp_servers.rhino-mcp]` 테이블, 주석 + 다른 테이블 보존 |
| `antigravity` | `~/.gemini/antigravity/mcp_config.json` |

기타 플래그: `--name`, `--config-path`(단일 클라이언트 지정 시에만), `--no-backup`, `--mode {auto,standalone,bridge}`, `--transport {stdio,http}`, `--launcher {auto,uvx,rhino-mcp,python}`, `--force`.
저장 전 기존 설정을 `.bak.<timestamp>` 로 백업.

### Rhino 안에서 — `_McpInstall`

브리지 플러그인 로드 상태에서 Rhino 명령창에 `_McpInstall` 입력.
ClaudeDesktop / ClaudeCode / Codex / Antigravity 토글 + All / Uninstall 제공, 초기 상태는 감지 결과.
`--launcher` 전달 → 모든 설정에 절대 경로 런처 기록.
런처마다 먼저 `--version` 을 확인해 플러그인 버전 이상을 제공하는 첫 런처 사용(uvx 는 `--from rhino3dm-mcp>=<플러그인 버전>`, 이어서 설치된 `rhino-mcp` 스크립트, 마지막으로 `python -m rhino_mcp.server`).
PyPI 배포 전에는 `uv tool install --force --from <rhino-mcp 경로> rhino3dm-mcp` 로 로컬 설치([troubleshooting](troubleshooting.md) 참고).
`rhino-mcp install` 자체도 PyPI 가 자기 버전을 제공할 때만 `uvx` 를 등록하고, 아니면 실행 중인 설치본을 가리키는 항목 기록.
런처 탐색 위치: `PATH` + `~/.local/bin`, `~/.cargo/bin`, `/opt/homebrew/bin`, `/usr/local/bin`.

## Rhino 측 브리지 플러그인 설치

브리지: Rhino 8 / Rhino 9 내부에서 실행되며 RhinoCommon + Grasshopper를 JSON-RPC 소켓으로 노출하는 C# Rhino 플러그인(`rhino_plugin/csharp/`).

```bash
./scripts/build-plugin.sh --release                 # Rhino 9 (기본), Rhino 9.app 으로 복사
./scripts/build-plugin.sh --release --rhino=8       # Rhino 8
./scripts/build-plugin.sh --release --rhino=both --no-install

# 같은 동작의 dotnet 직접 호출:
dotnet build rhino_plugin/csharp -c Release                    # Rhino 9 (기본)
dotnet build rhino_plugin/csharp -c Release -p:RhinoMajor=8    # Rhino 8
dotnet build rhino_plugin/csharp -c Release -p:SkipPluginCopy=true
```

MSBuild 속성 `RhinoMajor` 로 RhinoCommon / Grasshopper 참조 선택(`9` 는 9.0.26300.9401, `8` 은 8.36.26296.17001).
타깃 프레임워크는 양쪽 모두 `net8.0` 유지: Rhino 9 는 .NET 10 에서 실행되며 roll-forward 로 `net8.0` 플러그인 로드.
빌드 산출물: `rhino_plugin/csharp/bin/rh9/` 또는 `bin/rh8/` 아래 `rhino-mcp.rhp`.
`-p:SkipPluginCopy=true` 미지정 시 PostBuild 가 `/Applications/Rhino N.app`(macOS) 또는 `%APPDATA%/McNeel/Rhinoceros/N.0/Plug-ins/rhino-mcp/`(Windows)로 복사, 해당 Rhino 설치 존재 시에만 동작.

Package Manager: `./scripts/publish-yak.sh --rhino=8|9|both`(기본 `both`)가 `rh8`, `rh9` Yak 배포본을 각각 생성. Rhino 9 에서는 `rh9` 패키지 설치 필요, 잘못된 메이저용 빌드도 로드되지만 Python 측이 경고 로그 출력.

Rhino 뷰포트에 `.rhp` 드래그-앤-드롭(또는 `_PluginManager`)으로 1회 로드 → 플러그인이 TCP `127.0.0.1:4242`(추가 Rhino 인스턴스는 4257 까지의 다음 빈 포트)에서 JSON-RPC 리스너 시작.
MCP 서버 기동 시 자동 감지.

## Claude Desktop 수동 설정

`rhino-mcp install` 미사용 시 `claude_desktop_config.json` 편집(Claude Desktop → *Settings → Developer → Edit Config*):

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino3dm-mcp"],
      "env": {
        "RHINO_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Claude Desktop 재시작 후 도구 팔레트(palette)에 `rhino_*`/`gh_*` 도구 표시.

## 동작 확인

```bash
RHINO_MCP_FORCE_MODE=standalone uv run rhino-mcp --help
```

또는 MCP Inspector로:

```bash
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
