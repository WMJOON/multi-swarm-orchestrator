---
name: mso-process-template
description: |
  MSO 런타임의 프로세스 규약, 워크플로우 정의, Hand-off 템플릿을 제공하는 레퍼런스 스킬.
  워크트리 브랜치 프로세스, 단계 라우팅, 콜백 계약, 에러 택소노미를 정의한다.
  Loaded by the Governance layer as a process/convention reference.
disable-model-invocation: true
---

# mso-process-template

> MSO 런타임의 프로세스 규약·템플릿 레퍼런스.
> 불변 정책은 `rules/ORCHESTRATOR.md`에, 운영 상세는 [core.md](core.md)에 정의한다.

---

## 구성 파일

| 파일 | 설명 |
|------|------|
| [core.md](core.md) | 실행 모델, 워크트리 프로세스, work process, 단계 라우팅, 콜백 계약, 에러 택소노미, 인프라 노트 |
| [architecture.md](architecture.md) | Git-Metaphor 상태 모델, 전체 아키텍처, 업무/관제 공간, 버전별 주요 변경 |
| [pipelines.md](pipelines.md) | 설계·운영·인프라 파이프라인, CC-01~06 계약, 티켓 생명주기 |
| [getting-started.md](getting-started.md) | 디렉토리 구조, 설계·운영·검증 명령어 |
| [usage_matrix.md](usage_matrix.md) | Phase × Swarm × Role 매트릭스, 실행 흐름 시퀀스 |
| [changelog.md](changelog.md) | v0.0.3~v0.0.5 변경 이력 및 하위 호환 노트 |

---

## Hand-off 템플릿

| 템플릿 | 파일 | 용도 |
|--------|------|------|
| PRD | [templates/PRD.md](templates/PRD.md) | "왜 지금 이 방식인가" — Scenario 단위 요구사항 문서 |
| SPEC | [templates/SPEC.md](templates/SPEC.md) | 실행 계획 + 정책 + 티켓 리스트 + 체크리스트 |
| ADR | [templates/ADR.md](templates/ADR.md) | 아키텍처 의사결정 기록. 결정·대안·기각 사유·영향 추적 |
| HITL Escalation Brief | [templates/HITL_ESCALATION_BRIEF.md](templates/HITL_ESCALATION_BRIEF.md) | H1/H2 Gate 에스컬레이션 시 사람에게 전달하는 판단 요청서 |
| Run Retrospective | [templates/RUN_RETROSPECTIVE.md](templates/RUN_RETROSPECTIVE.md) | Run 완료 후 메트릭·교훈·이월 항목 회고 문서 |
| Design Handoff Summary | [templates/DESIGN_HANDOFF_SUMMARY.md](templates/DESIGN_HANDOFF_SUMMARY.md) | Design Swarm → Ops Swarm 인수인계 요약 문서 |
