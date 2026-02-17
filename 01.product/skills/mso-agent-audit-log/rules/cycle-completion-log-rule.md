# Rule: Cycle Completion Logging

## 1. 목적

업무 사이클 완료 시 다음 에이전트가 이어받을 수 있는 최소 컨텍스트를 남긴다.

---

## 2. 완료 조건

다음을 모두 만족하면 1회 완료로 본다.

1. 사용자 요청을 실제로 처리함
2. 사용자에게 결과를 반환하는 시점임
3. 확인 질문 대기 상태가 아님

---

## 3. 기록 원칙

- 완료 상태(`success/fail`)에서는 `context_for_next` 작성을 강권한다.
- `task_name`은 동사+목적어로 짧고 명확하게 작성한다.
- `action`은 수행 사실을 1줄로 작성한다.
- `continuation_hint`는 바로 실행 가능한 다음 액션으로 작성한다.

---

## 4. Quick Template

```sql
INSERT INTO audit_logs (
    id, date, task_name, mode, action,
    input_path, output_path, status, notes,
    context_for_next, continuation_hint
) VALUES (
    'TASK-001',
    date('now'),
    '[동사] [목적어]',
    '[project-mode]',
    '[1줄 요약]',
    '[입력 경로 또는 NULL]',
    '[출력 경로 또는 NULL]',
    'success',
    '[핵심 발견사항]',
    '[다음 에이전트가 알아야 할 것]',
    '[후속 작업 힌트 또는 NULL]'
);
```

---

## 5. 세션 시작 조회

```sql
-- 최근 작업
SELECT id, task_name, mode, status, notes,
       context_for_next, continuation_hint
FROM audit_logs
ORDER BY date DESC, id DESC
LIMIT 5;

-- 진행 중 작업
SELECT *
FROM audit_logs
WHERE status = 'in_progress'
ORDER BY date DESC;

-- 후속 작업 열린 건
SELECT *
FROM v_open_followups
LIMIT 10;
```

---

*Version: 1.2.0 | Portable — 프로젝트 독립적*
