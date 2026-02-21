---
workspace-id: sandbox|id
plan-id: id
scenario-id: id
worktree-id: none|id
worktree-name: null|text
update-at:
update-by:
create-at:
create-by:
---

# {work name} SPEC

## Object
1. Constraints / Assumptions

2. Risks / Open Questions

3. Functional

4. Non-Functional

5. Principles

---

## Execution

### Execution Policy

1. Retry Policy
에이전트 실행 실패 시 재시도 여부와 조건을 정의한다.
무한 재시도를 금지하며, 재시도 자체가 리스크가 되는 경우 명시적으로 False로 설정한다.

2. Timeout / Fallback
응답 지연 또는 오류 발생 시 중단 시점과 대체 경로를 정의한다.
fallback이 사람 개입인지, 다른 에이전트인지, 단순 종료인지 구분해 서술한다.

3. Human Override Point
자동 실행을 중단하고 사람의 판단이 개입되어야 하는 지점을 명시한다.
이는 예외가 아니라, 의도된 통제 지점으로 취급한다.

---

### Ticket List
단일 에이전트가 독립적으로 수행하기에 적합한 단위로 작업을 분해한다.
각 Ticket은 병렬 실행 가능 여부를 고려해 정의되어야 한다.

- {ticket-id}
	- [] Task:
	- [] Task:
티켓은 최소 실행 단위이며, 완료 여부가 명확히 판단 가능해야 한다.
티켓 간 의존성이 있다면 명시적으로 번호 또는 참조를 남겨야 합니다.

---

### Check List
Execution 완료 여부를 판단하기 위한 검증 항목이다.
Task 완료와 별도로, 전체 SPEC 관점에서의 충족 여부를 확인한다.

- []
- []

---

## Discussion

### {model name} Discussion
해당 SPEC에 대해 수행된 모델 기반 토론, critique, 대안 검토 내용을 기록한다.
결론뿐 아니라 반려된 아이디어도 남기는 것을 원칙으로 한다.
