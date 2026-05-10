# 환경 설정(Configuration)

`rhino-mcp`는 환경 변수와 소수의 CLI 플래그로만 설정.

## CLI 플래그

```
rhino-mcp [--transport {stdio,http}] [--host HOST] [--port PORT] [--version]
```

`--transport`는 `RHINO_MCP_TRANSPORT`를 override. `--host` / `--port`는 HTTP 전송에만 적용.

## 환경 변수

### MCP 서버 전송(transport)

| 변수                    | 기본값  | 비고 |
|-------------------------|---------|------|
| `RHINO_MCP_TRANSPORT`   | `stdio` | `stdio`(Claude Desktop) 또는 `http`(Streamable HTTP). `streamable-http`도 같은 의미. |
| `RHINO_MCP_LOG_LEVEL`   | `INFO`  | `DEBUG`/`INFO`/`WARNING`/`ERROR`. 로그는 항상 stderr로. |

### 브리지 연결(Rhino 측)

| 변수                            | 기본값            | 비고 |
|---------------------------------|-------------------|------|
| `RHINO_MCP_FORCE_MODE`          | _(자동)_          | `standalone`은 브리지 감지를 건너뜀, `bridge`는 브리지 도달 필수 — 실패 시 중단. |
| `RHINO_MCP_BRIDGE_OPTIONAL`     | `0`               | `1` + `FORCE_MODE=bridge` 시 브리지 미도달 → 중단 대신 standalone 폴백. |
| `RHINO_MCP_BRIDGE_TIMEOUT`      | `5`               | 자동 감지가 ping 응답을 기다리는 초. |
| `RHINO_MCP_RECONNECT_RETRIES`   | `3`               | 전송 실패 후 재연결 시도 횟수(지수 backoff). |
| `RHINO_MCP_REDETECT_COOLDOWN`   | `5`               | 지연 브리지 재감지(lazy promotion) 호출 간 최소 간격(초). |
| `RHINO_MCP_TRANSPORT_KIND`      | _(자동)_          | 브리지 전송 강제: `pipe` / `unix` / `tcp`. |
| `RHINO_HOST`                    | `localhost`       | 브리지 TCP 호스트. |
| `RHINO_PORT`                    | `4242`            | 브리지 TCP 포트. |
| `RHINO_MCP_PIPE`                | `rhino_mcp`       | Windows named pipe 인스턴스 이름. |
| `RHINO_MCP_SOCKET`              | _(XDG runtime)_   | Unix socket 경로. 기본 `$XDG_RUNTIME_DIR/rhino_mcp.sock`, 없으면 `/tmp/rhino_mcp.sock`. |
| `RHINO_MCP_KEEPALIVE_IDLE`      | `20`              | TCP keepalive idle 초 — OS가 peer probe 시작까지 대기. |
| `RHINO_MCP_KEEPALIVE_INTERVAL`  | `10`              | TCP keepalive probe 간격(초). |

### 서버 측(C# 브리지 플러그인)

| 변수                              | 기본값  | 비고 |
|-----------------------------------|---------|------|
| `RHINO_MCP_HEARTBEAT_INTERVAL`    | `10`    | long-running 핸들러(make2d, render, script execute 등) 동안 브리지가 송신하는 `rhino.heartbeat` notification 간격(초). socket idle 누적으로 인한 client keepalive 타임아웃 방지 목적. |
| `RHINO_MCP_UI_TIMEOUT`            | `30`    | UI thread dispatch 완료 대기 시간(초). 초과 시 timeout 에러 반환. |
| `RHINO_MCP_SEND_TIMEOUT_MS`       | `30000` | 브리지 socket send 타임아웃(ms). |

### 도구 안전성(Python 측)

| 변수                                | 기본값   | 비고 |
|-------------------------------------|----------|------|
| `RHINO_MCP_ALLOW_MODAL_COMMAND`     | _(off)_  | `1` 설정 시 `rhino_execute_python`의 modal `rs.Command` 패턴 사전 reject 비활성화 (`_Move`/`_Mirror`/`_Rotate`/`_Copy`/`_Scale`/`_SelLayer`/`_Layer _Assign` — bridge 단절 주된 원인). 디버깅 전용. |

## 전송 결정 로직

1. `--transport` / `RHINO_MCP_TRANSPORT`로 **MCP 전송**(stdio vs HTTP)을 결정.
2. **런타임 모드**(standalone vs bridge) 결정:
   - `RHINO_MCP_FORCE_MODE`가 설정되어 있으면 그것이 우선.
   - 그렇지 않으면 후보 브리지 전송을 우선순위로 시도(Windows: named pipe; macOS/Linux: unix socket; 폴백 TCP). `rhino.ping`에 응답하는 첫 번째가 채택됨.
   - 시간 안에 어떤 것도 응답하지 않으면 standalone으로 폴백.
3. 도구 등록은 v0.5.1+ 기준 항상 전체 모듈 등록 — 브리지 전용 도구는 호출 시점 가드(`require_bridge_only`)로 차단되거나 lazy promotion으로 자동 활성화.

## 배포 시나리오 예시

### Claude Desktop, Rhino 미설치

```json
{ "rhino-mcp": { "command": "uvx", "args": ["rhino3dm-mcp"],
                 "env": {"RHINO_MCP_FORCE_MODE": "standalone"} } }
```

### Claude Desktop과 같은 머신의 라이브 Rhino

기본 설정 — 자동 감지가 브리지를 찾음.

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
