---
name: mso-orchestrator-rule
description: Multi-swarm orchestrator policy and execution contract for v0.0.2 runtime workspace.
type: cursor-rule
version: 0.0.2
always_apply: false
---

# Multi-Swarm Orchestrator Rule (v0.0.2)

> 이 문서는 실행 가능한 스킬이 아니라 `multi-swarm-orchestrator`의 오케스트레이션 룰 문서다.
> Runtime Workspace(`workspace/.mso-context`)를 기준으로 단계·경로·체크포인트를 규정한다.

## 1) 기본 실행 모델
- 기본 모드: 문서 가이드 기반 수동 오케스트레이션
- 스킬 간 데이터 전달: Runtime Workspace 파일 아티팩트
- 감사/추적: `workspace/.mso-context/active/<Run ID>/`의 `manifest.json` + phase 산출물

## 2) 단계 라우팅
### 2.1 Design pipeline
- `mso-workflow-topology-design`
- `mso-mental-model-design`
- `mso-execution-design`

경로:
`workspace/.mso-context/active/<Run ID>/10_topology/workflow_topology_spec.json`
`→ workspace/.mso-context/active/<Run ID>/20_mental-model/mental_model_bundle.json`
`→ workspace/.mso-context/active/<Run ID>/30_execution/execution_plan.json`

### 2.2 Ops pipeline
- `mso-task-context-management` → 티켓 생성/상태 관리
- `mso-agent-collaboration` → 선택적 실행 레이어 (`run`/`batch`/`swarm`)

경로:
`workspace/.mso-context/active/<Run ID>/40_collaboration/task-context/tickets/TKT-0001.md`
`→ mso-agent-collaboration`
`→ *.agent-collaboration.json`

### 2.3 Infra pipeline
- `mso-agent-audit-log`(로그 소스)
- `mso-observability`(관측/feedback)

경로:
`workspace/.mso-context/active/<Run ID>/50_audit/agent_log.db`
`→ workspace/.mso-context/active/<Run ID>/60_observability/callback-*.json`
`→ mso-observability`

### 2.4 Governance pipeline
- `mso-skill-governance`

경로:
`workspace/.mso-context/active/<Run ID>/70_governance/`

## 3) 콜백/이벤트 계약
오케스트레이션 이벤트는 파일 기반 이벤트로 처리하고, 필수 필드가 모두 존재해야 한다.

- 필드: `event_type`, `checkpoint_id`, `payload`, `retry_policy`, `correlation`, `timestamp`
- 필수 이벤트 유형: `improvement_proposal`, `anomaly_detected`, `periodic_report`, `hitl_request`
- 출력 위치: `workspace/.mso-context/active/<Run ID>/60_observability/*.json`
- 수신자: `mso-observability`

## 4) Gate / HITL 규칙
- H1 Gate: 복잡도/리스크/비용 임계치 초과 시 `event_type=hitl_request`
- H2 Gate: 전략 변경 또는 topology 재작성 필요 시 `event_type=hitl_request`
- Gate 진입 시 `requires_manual_confirmation=true`
- 수동 승인은 Run 단위 산출물(`40_collaboration`, `70_governance`)에 기록

## 5) 에러/폴백 규칙
- `10/20/30` 또는 `50/60` 실행 실패 시 실패 채널에 에러 로그와 재시도 힌트 저장
- `mso-agent-collaboration` 외부 의존 미해결 시 fallback 출력 생성 후 파이프라인 계속
- CC 검증/정합 실패 시 `70_governance` 결과 기록 후 `manifest.status=failed`

## 6) 실행/검증 권장 절차
1. `python3 skills/mso-skill-governance/scripts/run_sample_pipeline.py --goal "..." --task-title "..." --skill-key msowd --case-slug "..."`
2. `python3 skills/mso-skill-governance/scripts/validate_schemas.py --skill-key msogov --case-slug "..." --json`
3. `python3 skills/mso-skill-governance/scripts/validate_cc_contracts.py --skill-key msogov --case-slug "..." --json`
4. `python3 skills/mso-skill-governance/scripts/validate_gov.py --skill-key msogov --case-slug "..." --json`
5. `python3 skills/mso-skill-governance/scripts/validate_all.py --case-slug "..."`

`validate_all`/`run_sample_pipeline` 등 스크립트는 Runtime Workspace 정책을 준수해 산출물을 생성/검증한다.
