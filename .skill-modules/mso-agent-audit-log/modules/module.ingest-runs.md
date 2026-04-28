# module.ingest-runs

## 질문 축

- 어떤 입력을 감사 로그로 어떻게 적재할 것인가?

## 입력 인터페이스

- JSON payload (권장):
  - `run_id`
  - `artifact_uri`
  - `status`
  - `errors`/`warnings` (배열)
  - `next_actions` (배열)
  - `metadata` (`source`, `schema_version`)
- Markdown 티켓(`create_ticket.py`)은 직접 추적되지 않으며, 티켓 식별자(`task_context_id` 또는 `id`)를 `input_path`로 연결한다.

## 기록 규칙

1. `task_id`가 없으면 `TASK-YYYYMMDD-NNN` 자동 생성.
2. `status`가 비정상일 때 `context_for_next`는 남겨야 한다.
3. 같은 `artifact_uri`/`run_id`에 대한 재적재는 기존 레코드를 덮어쓰기보다 `update` 우선 사용.
4. 실패 시 최소 필드도 남겨 운영자가 재개할 수 있게 한다.
