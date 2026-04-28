# mso-workflow-topology-design — Core Rules

## Terminology
| 용어 | 정의 |
|------|------|
| Topology | 목표 달성을 위한 노드 기반 실행 구조 |
| Node | 명시적 출력으로 추적되는 작업 단위 |
| θ_GT band | 노드의 의미적 불확실성 허용 폭 (`narrow`/`moderate`/`wide`) |
| RSV | 완료를 위해 닫아야 하는 Decision Question의 총량 |

## Input Interface
최소 입력:

- `goal` (string, required)
- 선택: `constraints`, `context`, `mode`(
`manual`, `semi_auto`, `auto`)

출력 경로 기본값: `{workspace}/.mso-context/active/<run_id>/10_topology/workflow_topology_spec.json`

## Output Interface
다음 필수 키를 가진 JSON:
- `run_id`
- `nodes`
- `edges`
- `topology_type`
- `rsv_total`

기타 키: `strategy_gate`, `metadata`.

Optional 키 (스키마에서 허용, 생성 시 권장):
- `decision_questions[]` — DQ별 id, question, weight
- `loop_risk_assessment[]` — 병리적 루프 위험 평가 (loop_type, where, risk, mitigation)
- `handoff_strategy` — hand-off 지점 및 컨텍스트 손실 최소화 규칙 (fan_out/fan_in/dag 전용)
- `execution_policy` — continue/reframe/stop 규칙, estimator 연동, human gate 노드

## Execution Model 선언 규약 (MUST — v0.1.2)

모든 노드에 `execution_model`을 선언한다. 런타임에 변경하지 않는다.

| Model | 구조 | 사용 조건 |
|-------|------|---------|
| `single_instance` | 하나의 에이전트가 여러 vertex를 순서대로 처리 | 순차 의존, 병렬 불필요 |
| `bus` | fan-out + 병렬 worker 에이전트 | 에이전트 간 조율 필요 |
| `direct_spawn` | 독립 에이전트들을 병렬 소환, merge에서 결과 수집 | 완전 독립 병렬 |

### 노드 선언 포맷 (MUST)

```yaml
node:
  id: <node_id>
  execution_model: single_instance   # single_instance | bus | direct_spawn

  # bus 선택 시 필수
  bus:
    pattern: fan_out                 # fan_out | pipeline | broadcast
    merge_policy: quorum             # quorum | first | all
    merge_agent: critic

  # optimizer가 채우는 영역 — 설계 시 반드시 null로 비워둔다 (MUST NOT 직접 채움)
  optimizer_hint:
    suggested_split_after: null
    compression_rate: null
    last_optimized: null
```

- `bus` 선택 시 `merge_policy` 필수 (MUST)
- `eval_point: true` 노드 명시 권장 (SHOULD)
- `optimizer_hint`는 `mso-workflow-optimizer` 실행 후 HITL 승인 시에만 갱신

## Processing Rules
1. 입력을 정제한 뒤 DQ를 생성하고 `rsv_total` 산출.
2. 목표 성격에 따라 topology 유형 선택( `linear` / `fan_out` / `fan_in` / `dag` / `loop`).
3. 각 Node의 `theta_gt_band`를 `wide`/`moderate`/`narrow`로 할당.
4. 노드에 `assigned_dqs`, `rsv_target`, `explicit_output`, **`execution_model`** 부여 (MUST).
5. `optimizer_hint`는 null로 초기화 (MUST).
6. `{workspace}/.mso-context/active/<run_id>/10_topology/workflow_topology_spec.json` 생성.

## Registry 해석 규칙 (Mode B)

workflow_registry 검색 시 해석 순서:
1. `~/.mso-registry/workflows/workflow_registry.json` (글로벌)
2. `{workspace}/.mso-context/workflow_registry.json` (워크스페이스 로컬)

## Error Handling
- `goal` 미제공: fail-fast.
- 목표를 DQ로 분해할 수 없는 경우: `when_unsure` 권고 메시지와 함께 실패/건너뛰기.
- 출력 스키마 위반: 즉시 실패.

## Security / Constraints
- 외부 경로를 임포트하지 않는다. pack 내부 상대경로만 사용한다.
- `goal` 원문은 `run_id` 생성에만 사용하고 로그에 과도한 민감정보를 남기지 않는다.

## when_unsure
- DQ 분해가 불안정하면 후보 기준(`동시성`, `리스크`, `복잡도`)을 제시하고 사용자 선택을 요청한다.
- `goal`이 과도하게 넓으면 단계별 분할 제안을 먼저 생성한다.
