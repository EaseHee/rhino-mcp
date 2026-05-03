# Grasshopper 가이드

모든 Grasshopper 도구는 브리지 전용. Rhino 8에 로드된 `RhinoMCPBridge.rhp` C# 플러그인으로 JSON-RPC 요청 전달.

## 사전 준비

1. Rhino 8 실행.
2. Grasshopper 창 한 번 이상 열기(캔버스 DocumentServer가 지연 초기화됨).
3. `RhinoMCPBridge.rhp`가 Rhino Plugin Manager에 로드된 상태(`dotnet build rhino_plugin/csharp -c Release` → 산출물 `.rhp` 드래그-드롭).
4. `RHINO_MCP_FORCE_MODE=bridge`로 `rhino-mcp` 실행.

## 캔버스 라이프사이클

```text
gh_open_file  → .gh / .ghx 로드
gh_new_canvas → 새 도큐먼트 시작
gh_save_file  → 현재 캔버스 저장
gh_reset      → 캐시된 솔루션(solution) 초기화
gh_run        → 재계산(기본은 새로운 솔루션 강제)
```

## 컴포넌트 추가

이름은 Grasshopper의 nickname 사전과 대소문자 무시 매칭됩니다. 모호하면 플러그인 접두사: `"Pufferfish.TweenCurves"`.

```jsonc
gh_add_component { "name": "Number Slider", "x": -100, "y": 0 }
gh_add_component { "name": "Move",          "x":  100, "y": 0 }
```

브리지가 새 컴포넌트의 GUID를 반환하므로, 이 GUID로 와이어를 연결합니다:

```jsonc
gh_connect_components {
  "from_component": "<slider_id>",  "from_output": 0,
  "to_component":   "<move_id>",    "to_input":   "T"
}
```

입출력은 0-기반 인덱스 또는 파라미터 nickname 모두 허용됩니다.

## 입력값 주입

| 위젯           | 도구                  | 비고 |
|----------------|-----------------------|------|
| Number Slider  | `gh_set_slider`       | 슬라이더 범위로 클램프(clamp) |
| Panel          | `gh_set_panel`        | 다중 라인 텍스트 지원 |
| Boolean Toggle | `gh_set_toggle`       | `true` / `false` |
| 일반 파라미터  | `gh_set_parameter`    | `GhParameterValue` 디스크리미네이터 사용 |

`GhParameterValue.type` ∈ `{number, integer, boolean, text, point, vector, plane, geometry_json}`. `geometry_json`은 rhino3dm `Encode()` JSON; 브리지가 Rhino 측에서 `Decode`합니다.

## 출력 읽기

```jsonc
gh_get_parameter { "component_id": "<id>", "output": "Result" }
```

단일 값 또는 평탄화된 리스트가 반환됩니다. 브랜치 구조가 중요할 때는 `gh_data_tree_get`:

```jsonc
gh_data_tree_get { "component_id": "<id>", "output": 0 }
// → {"branches": [{"path": [0,0], "values": [...]}, ...]}
```

`gh_data_tree_set`은 같은 구조를 받습니다:

```jsonc
gh_data_tree_set {
  "component_id": "<id>", "input": 0,
  "branches": [
    [{"indices":[0,0]}, [{"type":"number","value":1.5}, {"type":"number","value":3.0}]],
    [{"indices":[0,1]}, [{"type":"number","value":2.5}]]
  ]
}
```

## 베이크(Bake)

```jsonc
gh_bake_to_rhino { "component_ids": ["<id1>", "<id2>"], "layer": "Bake/Output" }
```

새로 추가된 Rhino 객체의 GUID를 반환합니다.

## Claude 세션 예시

```
You:  /work/wing.gh를 열고 실행해.
Claude: gh_open_file → gh_run

You:  'span' 슬라이더를 8에서 16까지 9스텝으로 스윕해서 각 결과를 새로운 레이어에 베이크해.
Claude:
   for s in [8, 9, ..., 16]:
       gh_set_slider {component_id: "<span>", value: s}
       gh_run        {new_solution: true}
       gh_bake_to_rhino {component_ids: ["<output>"], layer: f"Bake/{s}"}
```

## 문제 해결(Troubleshooting)

| 증상                                          | 해결 |
|-----------------------------------------------|------|
| `gh_component_missing`                        | 이름이 매치되지 않음. 플러그인 설치 또는 `gh_component_list`로 대체 검색. |
| `No active Grasshopper document.`             | Grasshopper 편집기를 한 번 이상 열어두세요. |
| 슬라이더 값이 의도와 다르게 클램프됨           | 슬라이더 도메인이 캔버스에서 정해져 있음. 캔버스에서 조정하거나, 추후 도구로 도메인 변경. |
| 베이크 결과가 0개                              | 현재 솔루션에 출력이 없음. `gh_run`을 먼저 실행하고 `gh_get_parameter`로 확인. |
