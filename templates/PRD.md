---
workspace-id: sandbox|id
plan-id: id
update-at:
update-by:
create-at:
create-by:
---

# {work name} PRD
## Object
### Background / Problem Statement
### Goals / Success Metrics
### Target Users / Personas
### In-Scope / Out-of-Scope

---

## Scenarios
### {Scenario-id}
#### Metadata
- worktree branch: True|False
해당 작업이 worktree branch를 필수로 요구하는지 여부를 명시한다.
workflow topology 변경, 공용 규칙 수정이 포함될 경우 True로 설정해야 한다.
- worktree id: {id}
실제 작업이 수행되는 worktree의 식별자이다.
- worktree name: {name}
사람이 식별하기 쉬운 이름을 사용하며, branch 이름과의 대응 관계가 드러나야 한다.

#### Object
1. Constraints / Assumptions
기술적·조직적·시간적 제약과 함께, 현재 SPEC이 성립하기 위해 암묵적으로 가정한 조건을 서술한다.
이후 변경 가능성이 있는 가정은 반드시 명시적으로 드러내야 한다.

2. Risks / Open Questions
아직 확정되지 않은 요소, 실패 가능성, 또는 실행 과정에서 판단이 필요한 지점을 정리한다.
해결되지 않은 상태로 남겨두는 것도 허용되지만, 인지된 리스크라는 점은 분명히 기록해야 한다.

3. Functional
에이전트 또는 시스템이 수행해야 할 기능적 요구사항을 나열한다.
"무엇을 한다" 수준에서 서술하며, 구현 방식은 여기서 강제하지 않는다.

4. Non-Functional
성능, 안정성, 비용, 보안, 관측 가능성 등 기능 외 요구사항을 정의한다.
이후 Execution Policy의 판단 기준으로 활용된다.

5. Principles
이 SPEC을 관통하는 설계 원칙을 명시한다.
트레이드오프 상황에서 어떤 선택을 우선해야 하는지 판단 기준을 제공해야 한다.

---

## Discussion
### {model name} discussion
