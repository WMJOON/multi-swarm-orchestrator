# Agent Audit Log Rule

## ⚠️ Log Clarification Rule

"로그"라는 표현이 나오면 먼저 대상 로그를 구분한다.

| 유형 | 의미 | 예시 위치 |
|------|------|-----------|
| **에이전트 로그** | 에이전트 작업/의사결정 기록 | `{workspace}/.mso-context/audit_global.db` |
| **도메인 로그** | 서비스/상담/이벤트 원천 데이터 | 프로젝트별 DB 또는 파일 |

모호하면 대상 로그를 먼저 확인한 뒤 진행한다.

---

## SQLite Only Policy

**에이전트 로그는 SQLite DB 단일 저장소로 운영한다.**

- 권장 DB: `{workspace}/.mso-context/audit_global.db`
- 마크다운 로그 파일 수동 중복 기록 금지

---

## Runtime Guards

```sql
PRAGMA foreign_keys = ON;
PRAGMA recursive_triggers = OFF;
```

---

## ID Convention

- `audit_logs.id`: `TASK-*`
- `decisions.id`: `DEC-*`

권장 포맷은 `TASK-001` / `DEC-001`이지만, 프로젝트 규칙에 맞춰 확장 가능하다.

```sql
-- 3자리 순번 포맷을 쓰는 팀의 예시
SELECT 'TASK-' || printf('%03d', COALESCE(MAX(CAST(SUBSTR(id,6) AS INT)),0)+1)
FROM audit_logs
WHERE id GLOB 'TASK-[0-9][0-9][0-9]';
```

---

## Schema Contract

### audit_logs
- `status`: `success / fail / in_progress`
- `transition_*`: `0/1`
- `context_for_next`: 완료 작업에서 **강권(권장)**

### document_references
- `reference_type`: `mention / read / edit / create`
- `referenced_by`: `user / agent`

---

## When to Log

- 작업 사이클 완료 시
- 실패/예외 발생 시
- 의사결정 기록이 필요한 시점

---

## Quick SQL

```sql
INSERT INTO audit_logs (
    id, date, task_name, mode, action, status, notes,
    context_for_next, continuation_hint
) VALUES (
    'TASK-001', date('now'), '[동사] [목적어]', '[mode]',
    '[1줄 요약]', 'success', '[핵심 발견사항]',
    '[다음 에이전트 컨텍스트]', '[후속 작업 힌트 또는 NULL]'
);

INSERT INTO decisions (id, date, title, context, decision_content, related_audit_id)
VALUES ('DEC-001', date('now'), '[제목]', '[배경]', '[결정 내용]', 'TASK-001');
```

---

## Health Check Queries

```sql
-- status 오염
SELECT id, status
FROM audit_logs
WHERE status NOT IN ('success', 'fail', 'in_progress');

-- 완료 작업인데 context_for_next 누락 (정책 위반 점검)
SELECT id, status
FROM audit_logs
WHERE status != 'in_progress'
  AND (context_for_next IS NULL OR trim(context_for_next) = '');

-- 문서 참조 enum 오염
SELECT id, reference_type, referenced_by
FROM document_references
WHERE reference_type NOT IN ('mention', 'read', 'edit', 'create')
   OR referenced_by NOT IN ('user', 'agent');
```

---

*Version: 1.5.0 | Portable — 프로젝트 독립적*

---

## Self-Recording Rules (v0.0.4)

에이전트는 작업 단위별로 자기 기록(1차)을 남겨야 한다. Hook은 점진적(2차)으로 도입한다.

| work_type | 기록 트리거 | 기록 단위 |
|-----------|------------|-----------|
| `execution` | 스크립트/파이프라인 실행 완료 | 1 run = 1 row |
| `modification` | 기존 파일 수정 | 파일 묶음 단위 |
| `structure` | 디렉토리/스키마 구조 변경 | 변경 세트 단위 |
| `document` | 문서 작성/편집 | 문서 1건 |
| `skill` | 스킬 정의 생성/수정 | 스킬 1건 |
| `error` | 오류 발생 및 해결 | 오류 1건 |
| `review` | 코드/문서 리뷰 | 리뷰 세션 1건 |

### 기록 제외 대상

- 단순 조회 (read-only 탐색)
- 짧은 Q&A (1-2 턴)
- 동일 작업의 미세 반복 (3초 이내 재시도)

---

## Merge Rules (v0.0.4)

- 동일 `work_type` + 동일 `files_affected` 조합이 연속 발생 → 단일 행으로 통합 가능
- **예외**: `status:fail` 또는 `work_type:error`인 행은 절대 병합하지 않는다
- 통합 시 `duration_sec`은 합산, `notes`는 마지막 값 유지

---

## Logging Policy (v0.0.4)

- `pattern_tag`는 비동기 배치로 할당 (실시간 부하 방지)
- 정책 조정(policy_change) 제안은 **사용자 승인 필수**
- 사용자가 제안을 거절하면 `suggestion_history.rejected_weight += 1.0` (마이너스 가중치)
- 3회 이상 거절된 패턴은 자동 제안에서 제외

---

## Worklog Operating Standards (v0.0.4)

인프라 작업(스키마 변경, 마이그레이션, CI/CD 수정)은 반드시 기록한다:
- `work_type`: `structure` 또는 `skill`
- `intent`: 변경 목적을 1줄로 명시
- `files_affected`: 변경된 파일 JSON 배열

---

## Feedback -> Decision/Evidence/Impact Auto Rule (v1.3.0)

사용자 피드백 입력 시 아래 3종은 자동으로 생성되어야 한다.

- `decisions` 1건 (`id = DEC-<feedback_id>`)
- `evidence` 1건 이상 (`type = user_feedback`)
- `impacts` 1건 이상 (기본 `domain = workflow`)

입력 테이블:

```sql
INSERT INTO user_feedback (
    id, date, user_id, feedback_text, source_ref_path,
    impact_domain, impact_summary, reversibility, related_audit_id
) VALUES (
    'FB-001', date('now'), 'user', 'HITL 기준 강화 필요',
    'notes/feedback.md', 'workflow', 'H1 승인 기준 누락', 'Medium', 'TASK-001'
);
```

검증 쿼리:

```sql
SELECT d.id, e.id AS evidence_id, i.id AS impact_id
FROM decisions d
JOIN evidence e ON e.decision_id = d.id
JOIN impacts i ON i.decision_id = d.id
WHERE d.id = 'DEC-FB-001';
```
