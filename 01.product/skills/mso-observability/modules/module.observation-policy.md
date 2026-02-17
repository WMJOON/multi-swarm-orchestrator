# module.observation-policy

## 신호 소스

- `audit_logs`(SQLite): 실행 상태/오류/재시도 패턴
- Behavior feed(JSONL) (옵션): 사용자 개입 힌트
- 실행 산출물: `workspace/.mso-context/active/<Run ID>/30_execution/execution_plan.json`

## 신호 정의(예시)

- `failure_cluster`: 동일 `task_name`의 연속 실패
- `retry_spike`: `transition_repeated=1` 비율 급증
- `bottleneck`: 단일 `task_name`의 이벤트 비율이 과도
- `human_deferral_loop`: `notes`/`continuation_hint`에서 수동개입 표현 탐지
- `rsv_inflation`: 기대 대비 실제 자원/진행 편차 (선택)
- `performance_drift`: 동일 작업군의 실행 분산 급증(경고)

## 출력
- 각 신호는 `workspace/.mso-context/active/<Run ID>/60_observability/signal_inventory.json`에 집계 후 callback 생성.
