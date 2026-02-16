# Agent Audit Log Rule

## ⚠️ Log Clarification Rule

"로그"라는 표현이 나오면 먼저 대상 로그를 구분한다.

| 유형 | 의미 | 예시 위치 |
|------|------|-----------|
| **에이전트 로그** | 에이전트 작업/의사결정 기록 | `agent_log.db` |
| **도메인 로그** | 서비스/상담/이벤트 원천 데이터 | 프로젝트별 DB 또는 파일 |

모호하면 대상 로그를 먼저 확인한 뒤 진행한다.

---

## SQLite Only Policy

**에이전트 로그는 SQLite DB 단일 저장소로 운영한다.**

- 권장 DB: `02.test/v0.0.1/agent_log.db`
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

*Version: 1.3.0 | Portable — 프로젝트 독립적*

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
