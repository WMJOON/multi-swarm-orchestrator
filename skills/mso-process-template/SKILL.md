---
name: mso-process-template
description: |
  MSO 런타임의 프로세스 규약, 워크플로우 정의, Hand-off 템플릿을 제공하는 레퍼런스 스킬.
  Use when worktree branch process, stage routing, callback contracts, or error taxonomy definitions are needed,
  or when the Governance layer requires process/convention reference lookup.
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

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| → | `mso-task-execution` | Runtime Role Registry + Fallback Policy Registry 제공 (정책 SoT) |

---

## 에이전트 역할 매핑 (Runtime Role Registry)

> `mso-task-execution`이 실행 중 에이전트 역할을 참조하는 SoT.

| Agent Role | Phase | 핵심 업무 |
|---|---|---|
| Provisioning | 1 | Worktree 초기화, Base Commit 생성 |
| Execution | 2 | 태스크 수행, 산출물 해싱(SHA-256) |
| Handoff | 2-3 | 노드 간 상태/해시 전달 |
| Branching | 3 | 분기 탐지/생성, 실험 경로 포크 |
| Critic/Judge | 3 | 머지 합의, 품질 평가 |
| Sentinel | 4 | 에러 식별, Checkout 복구, HITL 에스컬레이션 |

---

## 폴백 규칙 분류 체계 (Fallback Policy Registry)

> `mso-task-execution`이 에러 처리 시 참조하는 SoT. 정책 정의는 이 스킬이 소유하며, 실행 트리거는 `mso-task-execution`이 담당한다.

| 에러 유형 | severity | action | max_retry | requires_human |
|-----------|----------|--------|-----------|----------------|
| `schema_validation_error` | medium | retry | 3 | false |
| `hallucination` | high | retry → escalate | 2 | true (retry 소진 시) |
| `timeout` | low | retry | 2 | false |
| `hitl_block` | critical | escalate | 0 | true |

**action 정의:**
- `retry`: 동일 프롬프트 + 에러 메시지 첨부 후 재요청
- `escalate`: Sentinel Agent에 `hitl_request` 이벤트 전달
- `checkout`: 마지막 정상 커밋으로 워크스페이스 복구

`max_retry` 소진 후에도 해소되지 않으면 severity 한 단계 상향 후 `escalate`로 전환.
