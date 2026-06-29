# Workflow MOTIF Patterns

프로젝트 모든 워크플로우에서 반복되는 패턴(Motif) 정의. 새 워크플로우 작성 시 이 패턴을 따른다.

## Table of Contents

1. [Phase Structure Motif](#1-phase-structure-motif) — discovery/development/testing
2. [Step Definition Motif](#2-step-definition-motif) — location/deliverables/validation
3. [Decision Node Motif](#3-decision-node-motif) — decision_subject, 분기 조건
4. [Deliverable Taxonomy Motif](#4-deliverable-taxonomy-motif) — type 기반 분류
5. [Dependencies Motif](#5-dependencies-motif) — requires/provides
6. [Success Criteria Motif](#6-success-criteria-motif) — 표준 4차원
7. [Key Decisions Motif](#7-key-decisions-motif) — decision/rationale/status
8. [Quality Metrics Motif](#8-quality-metrics-motif) — 측정 가능 지표
9. [Workflow Patterns](#9-workflow-patterns-별도-문서) — MOTIF와의 구분
10. [Module-Specific Extensions](#10-module-specific-extensions) — 모듈 특화 섹션
11. [Timeline Motif (Optional)](#11-timeline-motif-optional) — Gantt 데이터
12. [When to Add New Motif](#12-when-to-add-new-motif)
13. [Usage Guide](#13-usage-guide-for-new-workflows)

---

## 1. Phase Structure Motif

모든 모듈 워크플로우는 동일한 3개 단계를 따릅니다.

### Structure
```yaml
module:
  name: [Module Name]
  id: [module-id]
  version: "1.0.0"
  description: [설명]
  owner: [Owner Email]
  created: [YYYY-MM-DD]

discovery:
  id: discovery
  label: 발견 & 계획
  status: completed | active | pending
  steps: [Step List]
  artifacts: [Artifact List]

development:
  id: development
  label: 개발 & 구현
  status: ...
  steps: [...]

testing:
  id: testing
  label: 테스트 & 평가
  status: ...
  steps: [...]
  success_criteria: [3개 이상]
```

### Phases Applied
| Phase | 빈도 | 필수 여부 |
|-------|------|---------|
| discovery | 6/6 (100%) | **Required** |
| development | 6/6 (100%) | **Required** |
| testing | 6/6 (100%) | **Required** |
| timeline | 5/6 (83%) | Optional |

---

## 2. Step Definition Motif

`type: step` 노드의 핵심 필드. **전체 문법은 [yaml-schema.md](yaml-schema.md) Section 3을 따른다.**

### 핵심 필드

| Field | Required | 설명 |
|-------|----------|------|
| `id` | ✓ | 불변 ID: `{module-abbr}-s-{NNN}` |
| `label` | ✓ | 표시 이름: `{동사} {목적어} [{맥락}]` |
| `status` | ✓ | `completed` \| `active` \| `pending` |
| `directories` | optional | input/output/reference/instruction 역할별 경로 |
| `deliverables` | optional | 이 step의 산출물 목록 |
| `validation` | optional | 품질 검증 항목 |
| `sub_steps` | optional | Mermaid 내부 subgraph용 상세 단계 |

### Example
```yaml
- type: step
  id: acp-s-006
  label: "hand-off 파일을 draft 폴더로 복제"
  status: active
  directories:
    - role: input
      path: 01.routing/
    - role: output
      path: 02.draft/
  deliverables:
    - "02.draft/: 복제된 작업 파일"
```

> 분기·판단이 필요한 지점은 `type: step`이 아닌 `type: decision` 노드로 분리한다.

---

## 3. Decision Node Motif

`type: decision` 노드에 `decision_subject` 필드로 판단 주체를 명시한다.
**전체 문법은 [yaml-schema.md](yaml-schema.md) Section 3, gate 시각화는 [gate-levels.md](gate-levels.md)를 따른다.**

### Subject Taxonomy

| Subject | 판단 주체 | 사용 예 |
|-------|-------------|--------|
| **user** | 사람/사용자가 process branch를 판단 | 정책 변경, 후보 artifact 선택, 골든셋 승인 |
| **agent** | agent가 process branch를 판단 | threshold routing, 자동 라우팅, 배치 판단 |

### Decision Quick-Path

```
판단 책임이 사람에게 있는가? → user
후보 artifact 선택/재생산 판단인가? → user
자동 routing case와 판단 기준이 명확한가? → agent
기준이 불명확하거나 운영 책임자가 직접 봐야 하는가? → user
```

### Example
```yaml
- type: decision
  id: acp-d-001
  label: "hand-off 확정 검토"
  decision_subject: user
  owner: owner@example.com
  sla: "24시간 이내"
  branches:
    - on: rejected
      goto: acp-s-007
```

---

## 4. Deliverable Taxonomy Motif

모든 워크플로우의 산출물은 **type** 기준으로 분류됩니다.

### Taxonomy
```yaml
deliverables:
  - type: [type-name]
    location: [path]
    status: [status]
    [type-specific-fields]
```

### Common Types
| Type | Fields | Examples |
|------|--------|----------|
| scripts | count, language | Python, SQL, bash |
| data | format, size, subfolders | CSV, JSON, Parquet |
| reports | categories, documents | Analysis, Extracts |
| documentation | sections, status | README, GUIDE |
| engine | components, metrics | Detection, Processing |
| framework | structure, guidelines | Policy, Architecture |

---

## 5. Dependencies Motif

모든 워크플로우는 다른 모듈과의 관계를 명시적으로 정의합니다.

### Structure
```yaml
dependencies:
  - requires: [Resource Name]
    source: [Source Module or External]
    status: [received|ready|pending]
    usage: [How this is used]

  - provides: [Output Name]
    consumers: [List of Consuming Modules]
    status: [ready|pending]
```

---

## 6. Success Criteria Motif

testing phase에 측정 가능한 기준 3개 이상을 포함합니다.

```yaml
success_criteria:
  - "[Module] 테스트 완료 (지표 ≥ 목표)"
  - "정확도 [N]% 이상"
  - "[스테이크홀더] 승인 획득"
```

---

## 7. Key Decisions Motif

핵심 의사결정을 근거와 함께 기록합니다.

```yaml
key_decisions:
  - decision: [What was decided]
    rationale: [Why this decision was made]
    status: [implemented|pending|reviewed]
```

---

## 8. Quality Metrics Motif

측정 가능한 품질 지표를 정의합니다.

```yaml
quality_metrics:
  - [metric_name]: [value]
```

---

## 9. Workflow Patterns (별도 문서)

MOTIF는 모든 step/phase에 **동일하게 적용되는 구조 단위**다.  
반면 **Workflow Pattern**은 형태(사이클)는 같지만 내용(예: "edit" 단계)이 워크플로우마다 다른 **더 큰 단위의 재사용 형태**다.

> MOTIF: Phase Structure, Step Definition, Decision Node, Dependencies... — 구조가 고정  
> Pattern: Local File Versioning, Git Versioning... — 구조는 고정, 내용은 모듈마다 다름

상세: [workflow-patterns.md](workflow-patterns.md)

---

## 10. Module-Specific Extensions

기본 Motifs 위에 모듈별 **특화된 섹션**을 추가합니다.

| Module | Extension | Purpose |
|--------|-----------|---------|
| 01.ingestion | agent_package | 분석 에이전트 패키지 정의 |
| 02.policy-engine | governance | 정책 버전 관리 및 변경 제어 |
| 03.data-masking | compliance | 규정 준수 항목 (GDPR, CCPA) |
| 04.vendor-x | communications | 협업 체계 및 연락처 |
| 10.RAG-Corpus-Dataset | data_governance | 저장, 접근, 백업 정책 |

---

## 11. Timeline Motif (Optional)

```yaml
timeline:
  - phase: [Phase Name]
    duration: [X주]
    status: [completed|active|pending]
    date: [YYYY-MM-DD to YYYY-MM-DD]
```

---

## 12. When to Add New Motif

새로운 Motif는 다음 조건에서 추가합니다:

1. **반복 빈도**: 3개 이상의 워크플로우에서 동일한 패턴이 반복
2. **정보 중요도**: 워크플로우의 핵심 정보를 체계적으로 정의
3. **쿼리 가능성**: 향후 자동 분석/쿼리 가능한 구조여야 함

---

## 13. Usage Guide for New Workflows

```yaml
# 1. Core Motifs
module:
  name: [Module Name]
  id: [module-id]

discovery:
  id: discovery
  steps: [...]

development:
  id: development
  steps:
    - type: step
      id: [mod]-s-001
      label: "..."
    - type: decision
      id: [mod]-d-001
      decision_subject: user | agent
      decision_criteria: [string]
      branches: [...]

testing:
  id: testing
  success_criteria: [3개 이상]

# 2. Dependencies
dependencies:
  - requires: [...]
  - provides: [...]

# 3. Key Decisions
key_decisions:
  - decision: [...]
    rationale: [...]
```
