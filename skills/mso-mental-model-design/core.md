# mso-mental-model-design — Core Rules

## Terminology
| 용어 | 정의 |
|---|---|
| mental_model_bundle | topology 결과를 실행 가능한 멘탈 모델로 번역한 계약 패키지 |
| local_charts | 노드별 판단 렌즈 목록 |
| execution_checkpoints | `preflight`/`pre_h1`/`pre_h2` 단계 |
| θ_GT (GT Angle) | 노드 출력의 의미적 분산 허용 폭. topology에서 상속받아 차트에 전파 |
| gt_angle_policy | θ_GT 적용 정책: `inherit` (상속) / `widen` (확대) / `override` (수동 지정) |

## Input Interface
- `workflow_topology_spec` 또는 goal 기반 입력을 받는다.
- 출력: `workspace/.mso-context/active/<Run ID>/20_mental-model/mental_model_bundle.json`

## Output Interface
필수 키:
- `run_id`, `domain`, `bundle_ref`, `local_charts`, `output_contract`, `node_chart_map`, `execution_checkpoints`

Optional 키 (스키마에서 허용, 생성 시 권장):
- `gt_angle_config` — 적용된 GT Angle 정책 (`default_policy`)
- `local_charts[].theta_gt_band` — 차트별 θ_GT band (narrow/moderate/wide)
- `local_charts[].theta_gt_range` — 차트별 θ_GT 수치 범위 {min, max}
- `local_charts[].semantic_entropy_expected` — 예상 의미 엔트로피
- `local_charts[].gt_angle_policy` — 해당 차트에 적용된 정책

## Processing Rules
1. 입력 토폴로지에서 각 노드 id를 추출한다.
2. 노드당 최소 1개 이상의 chart를 생성한다.
3. `execution_checkpoints.stage`는 `preflight` 기본값.
4. `node_chart_map`에서 topology node가 참조하는 chart가 빈 배열이 되지 않도록 보장한다.

## Error Handling
- topology가 비었거나 노드가 부재하면 fail-fast.
- `local_charts`가 비면 fail-fast.
- 스키마 위반은 즉시 보고하고 중단.

## when_unsure
- 도메인이 애매하면 `domain`를 `General`로 설정하고, 가정 사항을 `metadata.assumptions`에 기록.
