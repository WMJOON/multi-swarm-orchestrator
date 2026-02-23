---
workspace-id: sandbox|id
plan-id: id
discussion-required: false
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

> **시나리오 분기 기준**
>
> 시나리오는 **서로 대치되는 접근 방식(Trade-off가 존재하는 대안)**이 있을 때만 복수로 작성한다.
> - **복수 시나리오 O**: 구현 전략이 다르고, 둘 중 하나만 선택해야 하는 경우
> - **복수 시나리오 X**: 단계적으로 순서대로 실행해야 하는 작업 → 단일 시나리오의 **Phases**로 정의
>
> 잘못된 예: Phase 1 → Phase 2 → Phase 3을 각각 Scenario-A, B, C로 분리하는 것
> 올바른 예: "직접 구현 vs 외부 라이브러리 도입"처럼 선택이 갈리는 경우에만 복수 시나리오 사용

### {Scenario-id}: {대안 이름}

> 이 시나리오를 선택하는 이유와 포기하는 것을 한 줄로 요약한다.
> 예: "빠른 출시를 우선한다 — 대신 확장성을 일부 포기한다."

#### Metadata
- worktree branch: True|False
해당 작업이 worktree branch를 필수로 요구하는지 여부를 명시한다.
workflow topology 변경, 공용 규칙 수정이 포함될 경우 True로 설정해야 한다.
- worktree id: {id}
실제 작업이 수행되는 worktree의 식별자이다.
- worktree name: {name}
사람이 식별하기 쉬운 이름을 사용하며, branch 이름과의 대응 관계가 드러나야 한다.

#### Phases (순차 실행 단계)
순서대로 실행해야 하는 작업이 있다면 여기에 정의한다. 각 Phase는 독립적인 시나리오가 아니라 하나의 흐름 안의 단계다.

- Phase 1: {단계명} — {한 줄 설명}
- Phase 2: {단계명} — {한 줄 설명}
- Phase N: ...

단계 구분이 불필요하면 이 섹션을 생략한다.

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
