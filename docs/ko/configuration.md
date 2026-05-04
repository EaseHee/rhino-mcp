# 환경 설정(Configuration)

`rhino-mcp`는 환경 변수와 소수의 CLI 플래그로만 설정합니다.

## CLI 플래그

```
rhino-mcp [--transport {stdio,http}] [--host HOST] [--port PORT] [--version]
```

`--transport`는 `RHINO_MCP_TRANSPORT`를 덮어씁니다. `--host` / `--port`는 HTTP 전송에서만 적용됩니다.

## 환경 변수

### MCP 서버 전송(transport)

| 변수                    | 기본값  | 비고 |
|-------------------------|---------|------|
| `RHINO_MCP_TRANSPORT`   | `stdio` | `stdio`(Claude Desktop) 또는 `http`(Streamable HTTP). `streamable-http`도 같은 의미. |
| `RHINO_MCP_LOG_LEVEL`   | `INFO`  | `DEBUG`/`INFO`/`WARNING`/`ERROR`. 로그는 항상 stderr로. |

### 브리지 연결(Rhino 측)

| 변수                          | 기본값            | 비고 |
|-------------------------------|-------------------|------|
| `RHINO_MCP_FORCE_MODE`        | _(자동)_          | `standalone`은 브리지 감지를 건너뜀, `bridge`는 브리지 도달 필수 — 실패 시 중단. |
| `RHINO_MCP_BRIDGE_TIMEOUT`    | `1`               | 자동 감지가 ping 응답을 기다리는 초. |
| `RHINO_MCP_TRANSPORT_KIND`    | _(자동)_          | 브리지 전송 강제: `pipe` / `unix` / `tcp`. |
| `RHINO_HOST`                  | `localhost`       | 브리지 TCP 호스트. |
| `RHINO_PORT`                  | `4242`            | 브리지 TCP 포트. |
| `RHINO_MCP_PIPE`              | `rhino_mcp`       | Windows named pipe 인스턴스 이름. |
| `RHINO_MCP_SOCKET`            | _(XDG runtime)_   | Unix socket 경로. 기본 `$XDG_RUNTIME_DIR/rhino_mcp.sock`, 없으면 `/tmp/rhino_mcp.sock`. |

## 전송 결정 로직

1. `--transport` / `RHINO_MCP_TRANSPORT`로 **MCP 전송**(stdio vs HTTP)을 결정.
2. **런타임 모드**(standalone vs bridge) 결정:
   - `RHINO_MCP_FORCE_MODE`가 설정되어 있으면 그것이 우선.
   - 그렇지 않으면 후보 브리지 전송을 우선순위로 시도(Windows: named pipe; macOS/Linux: unix socket; 폴백 TCP). `rhino.ping`에 응답하는 첫 번째가 채택됨.
   - 시간 안에 어떤 것도 응답하지 않으면 standalone으로 폴백.
3. 도구 등록은 런타임 모드를 참고하며, 브리지 전용 도구는 standalone에서 등록되지 않습니다.

## 배포 시나리오 예시

### Claude Desktop, Rhino 미설치

```json
{ "rhino-mcp": { "command": "uvx", "args": ["rhino3dm-mcp"],
                 "env": {"RHINO_MCP_FORCE_MODE": "standalone"} } }
```

### Claude Desktop과 같은 머신의 라이브 Rhino

기본 설정 — 자동 감지가 브리지를 찾습니다.

### 워크스테이션의 원격 Rhino + Docker 컨테이너의 MCP 서버

```yaml
services:
  rhino-mcp:
    image: rhino-mcp:latest
    environment:
      RHINO_MCP_TRANSPORT: http
      RHINO_MCP_FORCE_MODE: bridge
      RHINO_MCP_TRANSPORT_KIND: tcp
      RHINO_HOST: workstation.local
      RHINO_PORT: 4242
    ports: ["8765:8765"]
```

### 헤드리스 CI

```bash
RHINO_MCP_FORCE_MODE=standalone pytest
```
