---
description: |
  Immutable policies and invariants for multi-swarm orchestrator v0.0.5 runtime.
alwaysApply: true
---

# Multi-Swarm Orchestrator Policy (v0.0.5)

> 이 문서는 불변 정책만 정의한다. 운영 상세(라우팅, 프로세스, 템플릿, 에러 분류, 인프라)는 `skills/mso-orchestrator/SKILL.md`를 참조한다.

## 1) 용어 정의

### Worktree 관련 용어

| 용어                  | 정의                                                                                                                                                                                                                   |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **branch**            | worktree는 항상 특정 branch에 연결되어야 한다. branch는 작업의 논리적 단위를 의미하며, 실험·변경·검토가 필요한 모든 작업은 branch 단위로 분리해야 한다. 이를 통해 main의 안정성을 유지하고, 병렬 작업을 가능하게 한다. |
| **pull request (PR)** | worktree branch에서 수행한 작업 결과를 workspace main으로 반영하기 위한 공식 검토 단위다. PR은 단순 병합 요청이 아니라, 계획·의도·변경 범위를 설명하는 커뮤니케이션 인터페이스로 취급한다.                             |
| **merge**             | 검토가 완료된 branch를 main에 반영하는 행위다. merge는 자동화될 수 있으나, workflow 변경이 포함된 경우에는 human approval을 필수로 요구해야 한다.                                                                      |

## 2) Workspace Main 사용 원칙

workspace의 main에서는 직접 작업을 지양해야 한다. 특히 다음 유형의 작업은 반드시 worktree branch process를 통해서만 진행해야 한다.

- workflow topology 변경
- agent orchestration 규칙 수정
- execution order, dependency, concurrency 변경
- 공용 template(PRD, SPEC, Skill 등) 수정

이는 단순한 Git 규칙이 아니라, Agentic Workflow의 안정성과 재현성을 유지하기 위한 운영 규칙이다.

## 3) Gate / HITL 정책

- H1 Gate: 복잡도/리스크/비용 임계치 초과 시 `event_type=hitl_request`
- H2 Gate: 전략 변경 또는 topology 재작성 필요 시 `event_type=hitl_request`
- Gate 진입 시 `requires_manual_confirmation=true`
- 수동 승인은 Run 단위 산출물(`40_collaboration`, `70_governance`)에 기록

## 4) 복구 정책

- 복구 시 모호한 상대 참조(`HEAD~1`) 금지 — 오직 절대 불변 커밋 참조(Absolute SHA)만 사용
- 무한 재시도 금지 — 모든 retry에는 `max_retry` 상한이 필수
- CC 검증/정합 실패 시 `70_governance` 결과 기록 후 `manifest.status=failed`

## 5) Role-Skill 바인딩 정책

에이전트 세션/인스턴스는 자신의 역할에 따라 아래 스킬을 반드시 로드해야 한다.
운영 상세(스킬 간 데이터 흐름, 경로 규약)는 `skills/mso-process/SKILL.md` 섹션 5를 참조한다.

### 5.1 Swarm(파이프라인) 기준

| Swarm        | Required Skills                                                                   |
| ------------ | --------------------------------------------------------------------------------- |
| Design Swarm | `mso-workflow-topology-design`, `mso-mental-model-design`, `mso-execution-design` |
| Ops Swarm    | `mso-task-context-management`, `mso-agent-collaboration`                          |
| Infra        | `mso-agent-audit-log`, `mso-observability`                                        |
| Governance   | `mso-skill-governance`, `mso-process`                                             |

### 5.2 Phase × Role 기준

| Phase | Role               | Swarm      | Required Skills                                  |
| ----- | ------------------ | ---------- | ------------------------------------------------ |
| 1     | Provisioning Agent | Ops        | `mso-task-context-management`                    |
| 2     | Execution Agent    | Ops        | `mso-agent-collaboration`, `mso-agent-audit-log` |
| 2     | Handoff Agent      | Ops        | `mso-execution-design`                           |
| 3     | Branching Agent    | Design     | `mso-workflow-topology-design`                   |
| 3     | Handoff Agent      | Ops        | `mso-execution-design`                           |
| 3     | Critic/Judge Agent | Infra      | `mso-observability`                              |
| 4     | Sentinel Agent     | Infra      | `mso-agent-audit-log`, `mso-observability`       |

- 동일 role이 복수 phase에 등장할 경우 스킬 집합은 합산된다.
- Swarm 기준과 Phase×Role 기준이 충돌하면 Phase×Role 기준을 우선한다.
