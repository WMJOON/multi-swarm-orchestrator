---
name: mso-observability
description: |
  Reads execution SoT (audit-log) to analyze patterns and generates HITL checkpoints and improvement proposals.
  Use when execution logs need pattern analysis, anomaly detection, or improvement proposals.
  v0.0.4: Adds work_type imbalance, pattern_tag candidate, and error hotspot detection signals.
disable-model-invocation: true
---

# mso-observability

> 이 스킬은 SoT를 읽기 전용으로 소비한다. 자동 반영(토폴로지 수정 등)은 수행하지 않고 제안만 남긴다.

---

## 핵심 정의

| 개념 | 정의 |
|------|------|
| **SoT consumer** | `workspace/.mso-context/audit_global.db`를 읽기만 함 (레거시: `active/<Run ID>/50_audit/agent_log.db`). 쓰기는 `mso-agent-audit-log` 전용 |
| **callback event** | `workspace/.mso-context/active/<Run ID>/60_observability/` 디렉토리에 기록되는 JSON 이벤트 파일 |
| **event_type** | `improvement_proposal`, `anomaly_detected`, `periodic_report`, `hitl_request`, `branch_created`, `merge_completed`, `checkout_executed`, `snapshot_committed` |
| **HITL checkpoint** | 사용자 개입이 필요한 시점. event로 기록되며 승인 전까지 파이프라인 대기 |

---

## 실행 프로세스

### Phase 1: SoT 로딩

1. `workspace/.mso-context/audit_global.db` 경로를 runtime 규칙으로 resolve (레거시 fallback: `active/<Run ID>/50_audit/agent_log.db`)
2. DB 미존재 → `event_type: periodic_report` + `severity: warning` 이벤트 기록 후 종료
3. `audit_logs` 테이블에서 최근 N건(기본 100) 조회
4. `node_snapshots` 테이블에서 현재 Run의 스냅샷 조회 (v0.0.4)
5. v1.5.0 확장 컬럼 조회 시도 (`work_type`, `pattern_tag`, `duration_sec`, `files_affected`, `session_id`, `intent`), 실패 시 구 스키마 fallback (v0.0.4)

**when_unsure**: DB 경로 불명 → runtime 기본 경로를 우선 사용.

### Phase 2: 패턴 분석

1. **실행 패턴**: 성공/실패 비율, 반복 실패 스킬
2. **병목 탐지**: 평균 실행 시간 대비 이상치 노드
3. **비용 이상**: 특정 스킬의 과도한 호출 빈도
4. **루프 탐지**: 동일 `run_id`의 반복 실패 패턴
5. **스냅샷 패턴 분석** (v0.0.4):
   - 분기 빈도: 동일 Run 내 branch 노드 생성 횟수
   - 머지 충돌 빈도: merge 노드에서 manual_review_required 발생 비율
   - 롤백 빈도: rolled_back 상태 스냅샷 비율
   - 브랜치 수명: 생성~머지/삭제 간 평균 시간
6. **v0.0.4 패턴 분석** (work_type 기반):
   - `detect_work_type_imbalance`: 단일 work_type > 50% → `improvement_proposal`
   - `detect_pattern_tag_candidates`: (work_type, files_affected) 3회+ 반복 → `improvement_proposal`
   - `detect_error_hotspots`: fail 로그의 파일 2회+ → `anomaly_detected`

### Phase 3: 이벤트 생성

1. 분석 결과를 callback event JSON으로 변환
2. 각 이벤트에 필수 키 채움:
   - `event_type`, `checkpoint_id`, `payload` (target_skills, severity, message)
   - `retry_policy`, `correlation` (run_id, artifact_uri), `timestamp`
3. `workspace/.mso-context/active/<Run ID>/60_observability/callback-<timestamp>-<seq>.json`에 기록
4. Critical 이벤트 → `hitl_request`로 상향
5. 확장 이벤트:
   - `branch_created`: 새 브랜치 분기 시
   - `merge_completed`: 성공적 머지 완료 시
   - `checkout_executed`: 폴백 롤백 실행 시
   - `snapshot_committed`: 노드 스냅샷 커밋 시

### Phase 4: 개선 제안 (선택적)

1. 반복 실패 패턴 → `improvement_proposal` 생성
2. target_skills에 개선 대상 스킬 명시
3. **자동 적용하지 않음** — 사용자 검토 후 Design 스킬에 수동 반영

**when_unsure**: 신호가 불명확하면 `periodic_report`로 빈 요약을 남기고, "수동 점검 권장" 기록.

**산출물**: `workspace/.mso-context/active/<Run ID>/60_observability/callback-*.json`, `workspace/.mso-context/active/<Run ID>/60_observability/callbacks-*.json` (집계)

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-agent-audit-log` | CC-05: audit DB를 읽기 전용 소비 |
| → | `mso-workflow-topology-design` | 환류: topology 노드 구조 개선 제안 (사용자 승인 필요) |
| → | `mso-mental-model-design` | 환류: chart/checkpoint 조정 제안 (사용자 승인 필요) |

---

## Templates

템플릿 SoT: `mso-process-template/templates/`

| 템플릿 | 파일 | 용도 |
|--------|------|------|
| **HITL Escalation Brief** | [../mso-process-template/templates/HITL_ESCALATION_BRIEF.md](../mso-process-template/templates/HITL_ESCALATION_BRIEF.md) | H1/H2 Gate 에스컬레이션 시 사람에게 전달하는 판단 요청서 |
| **Run Retrospective** | [../mso-process-template/templates/RUN_RETROSPECTIVE.md](../mso-process-template/templates/RUN_RETROSPECTIVE.md) | Run 완료 후 메트릭·교훈·이월 항목을 종합하는 회고 문서 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| **Portfolio Status 생성** | `python3 scripts/generate_portfolio_status.py` |
| observation 수집 실행 | `python3 scripts/collect_observations.py` |
| callback 스키마 검증 | [schemas/observability_callback.schema.json](schemas/observability_callback.schema.json) |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |

### Portfolio Status 출력 예시

`generate_portfolio_status.py`는 다음 데이터를 조합하여 하나의 markdown 문서를 생성한다:

| 섹션 | 데이터 소스 |
|------|------------|
| Summary | tickets/*.md frontmatter 상태 집계 |
| Ticket Status | 티켓별 status/priority/owner/due_by |
| Audit Logs | `workspace/.mso-context/audit_global.db` 성공/실패/진행 중 카운트 |
| Snapshots | `node_snapshots` 테이블 — 노드 타입별 분포, 상태별 집계 (v0.0.4) |
| Assignments | *.agent-collaboration.json dispatch 결과 |
| Workflow Map | workflow_topology_spec.json → Mermaid 자동 렌더링 |
