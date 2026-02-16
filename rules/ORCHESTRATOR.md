---
name: mso-orchestrator-rule
description: Multi-swarm orchestrator policy and execution contract for v0.0.1.
type: cursor-rule
version: 0.0.1
always_apply: false
---

# Multi-Swarm Orchestrator Rule (v0.0.1)

> **정의**: 이 문서는 실행 가능한 스킬이 아니라 `multi-swarm-orchestrator`의 **오케스트레이션 룰 문서**입니다.
> `SKILL.md`처럼 직접 `/run`/`/batch`를 호출하는 엔트리포인트가 아니며, 오케스트레이션 정책·라우팅·체크포인트를 규정합니다.

## 1) 기본 실행 모델
- 기본 모드: **문서 가이드 기반 수동 오케스트레이션**
- 스킬 간 데이터 교환: 파일 시스템 artifact
- 감사/추적: `metadata` + `../02.test/v0.0.1/*`의 실행 산출물

## 2) 단계 라우팅
### 2.1 Design pipeline
- `mso-workflow-topology-design`
- `mso-mental-model-design`
- `mso-execution-design`

경로:
`goal.json / input.md`
`→ ../02.test/v0.0.1/outputs/workflow_topology_spec.json`
`→ ../02.test/v0.0.1/outputs/mental_model_bundle.json`
`→ ../02.test/v0.0.1/outputs/execution_plan.json`

### 2.2 Ops pipeline
- `mso-task-context-management` → 티켓 생성/상태 관리
- `mso-agent-collaboration` → 선택적 실행 레이어 (`run`/`batch`/`swarm`)

경로:
`../02.test/v0.0.1/task-context/tickets/TKT-0001.md`
`→ mso-agent-collaboration`
`→ output-report.json`
`→ run-manifest.json`

### 2.3 Infra pipeline
- `mso-agent-audit-log`(로그 소스)
- `mso-observability`(관측/feedback)

경로:
`mso-agent-audit-log`
`→ ../02.test/v0.0.1/observations/*.json`
`→ mso-observability`

### 2.4 Governance pipeline
- `mso-skill-governance`

경로:
`schemas + skill core/modules + outputs/*`
`→ governance_report.md`

## 3) 콜백/이벤트 계약
오케스트레이션 이벤트는 파일 기반 이벤트로 처리하고, 필수 필드가 모두 존재해야 합니다.

- 필드: `event_type`, `checkpoint_id`, `payload`, `retry_policy`, `correlation`, `timestamp`
- 필수 이벤트 유형: `improvement_proposal`, `anomaly_detected`, `periodic_report`, `hitl_request`
- 출력 위치: `../02.test/v0.0.1/observations/*.json`
- 수신자: `mso-observability`만이 이벤트를 소비

## 4) Gate / HITL 규칙
- H1 Gate: 복잡도/리스크/비용 임계치 초과 시 `event_type=hitl_request` 발행
- H2 Gate: 전략 변경 또는 topology 재작성 필요 시 `event_type=hitl_request` 발행
- Gate 진입 시 오케스트레이션은 `requires_manual_confirmation=true` 상태로 남김
- 수동 승인은 `02.test/v0.0.1` 산출물에 승인/반려 이력으로 영속화

## 5) 에러/폴백 규칙
- `00/01/02` 또는 `05/06` 실행 실패 시, 실패 채널에 에러 로그와 재시도 힌트를 저장
- `mso-agent-collaboration`에서 외부 의존 미해결 시 `fallback` 출력 생성 후 파이프라인은 계속 진행
- CC 검증/정합 실패 시 `governance_report.md`의 `FAIL` 섹션 기록 후 중단 상태 전환

## 6) 실행/검증 권장 절차
1. `python3 skills/mso-workflow-topology-design/scripts/generate_topology.py --goal ... --output ../02.test/v0.0.1/outputs/workflow_topology_spec.json`
2. `python3 skills/mso-mental-model-design/scripts/build_bundle.py --topology ../02.test/v0.0.1/outputs/workflow_topology_spec.json --output ../02.test/v0.0.1/outputs/mental_model_bundle.json`
3. `python3 skills/mso-execution-design/scripts/build_plan.py --topology ../02.test/v0.0.1/outputs/workflow_topology_spec.json --bundle ../02.test/v0.0.1/outputs/mental_model_bundle.json`
4. `python3 skills/mso-task-context-management/scripts/create_ticket.py --path ../02.test/v0.0.1/task-context --title ...`
5. `python3 skills/mso-agent-collaboration/scripts/dispatch.py --ticket ../02.test/v0.0.1/task-context/tickets/TKT-0001.md --task-dir ../02.test/v0.0.1/task-context`
6. `python3 skills/mso-task-context-management/scripts/archive_tasks.py --path ../02.test/v0.0.1/task-context`
7. `python3 skills/mso-observability/scripts/generate_portfolio_status.py`
8. `python3 skills/mso-skill-governance/scripts/validate_all.py`
9. `python3 skills/mso-skill-governance/scripts/run_sample_pipeline.py`

`validate_all`, `run_sample_pipeline` 등 스크립트 실행은 이 룰을 준수해 산출물을 생성/검증합니다.
