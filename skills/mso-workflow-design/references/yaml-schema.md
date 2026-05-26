# Workflow YAML Schema

## 설계 원칙

- **YAML이 SSOT** — md는 YAML 변환 산출물. 직접 편집 금지.
- **id는 불변** — worklog·auditlog의 추적 키. 한번 부여하면 변경 금지.
- **label은 표시용** — 사람이 읽는 이름. id와 분리되어 변경 가능.

---

## Table of Contents

1. [ID 체계](#1-id-체계)
2. [Label 패턴](#2-label-패턴)
3. [Node Types](#3-node-types)
4. [Directory Roles](#4-directory-roles)
5. [Decision Branch Conditions](#5-decision-branch-conditions)
6. [Phase Schema](#6-phase-schema)
7. [Full Example](#7-full-example)

---

## 1. ID 체계

### 스킬이 강제하는 것
- 모든 step·decision·group 노드에 `id` 존재
- `id` 는 워크플로우 내 unique
- 한번 부여된 id 는 변경 금지 (worklog/auditlog 추적 키)

### 프로젝트가 정의하는 것
- id 네이밍 패턴 (예: `{module-abbr}-{type-code}-{NNN}`)
- 모듈 약어 매핑
- type code 표기 (`s`/`d`/`g` 등)

> 예시는 [assets/conventions-example.md](../assets/conventions-example.md) 참고.

본 문서 이하의 예시 ID(`acp-s-001` 등)는 **AI Chatbot 1.0 프로젝트 컨벤션 기준** 예시이며,
스킬이 강제하는 형식이 아니다.

---

## 2. Label 패턴

label은 auditlog에서 사람이 읽는 행위 설명. `{동사} {목적어} [{맥락}]` 패턴.

```
패턴: {verb} {object} [{context}]

예:
  "draft 파일 수정"
  "hand-off 파일을 draft 폴더로 복제"
  "hand-off 확정 검토"
  "기존 파일을 history로 이동"
  "응답 품질 평가"
```

### 동사 사전 (권장)

| 동사 | 의미 |
|------|------|
| 분석 | 입력을 읽고 결과 도출 |
| 생성 | 새 산출물 작성 |
| 수정 | 기존 파일 변경 |
| 복제 | 파일 복사 |
| 이동 | 파일 위치 변경 |
| 검토 | 판단/승인 (decision 전용) |
| 평가 | 측정·채점 (decision 전용) |
| 검증 | 품질 확인 |

---

## 3. Node Types

### step

실행 작업 노드. I/O는 선택적.

```yaml
- type: step
  id: acp-s-001               # 필수, 불변
  label: "draft 파일 수정"     # 필수
  status: completed | active | pending
  directories:                # Optional
    - role: input | output | reference | instruction
      path: [path]
  deliverables: [list]        # Optional
  validation: [list]          # Optional
  sub_steps: [list of string] # Optional — Mermaid inner subgraph
```

### decision

분기/판단 노드. `automation_gate`가 여기에 속함.

```yaml
- type: decision
  id: acp-d-001
  label: "hand-off 확정 검토"
  judge: HITL | HITLFE | HOTL | HOOTL
  # judge별 추가 필드 (아래 참조)
  branches:
    - on: [condition]          # judge별 허용 조건 (Section 5 참조)
      goto: [node-id]          # 생략 시 → sequential next
```

**HITL 추가 필드:**
```yaml
judge: HITL
owner: [email]                 # 필수
sla: "24시간 이내"             # Optional
```

**HITLFE 추가 필드:**
```yaml
judge: HITLFE
owner: [email]                 # 필수
threshold: "confidence < 0.85" # 필수 — 에스컬레이션 조건
sla: [string]                  # Optional
```

### group

여러 노드를 Mermaid subgraph로 묶는 컨테이너.

```yaml
- type: group
  id: acp-g-001
  label: "정책 업데이트 사이클"
  steps:                       # step | decision | group 재귀 중첩 가능
    - type: step
      ...
    - type: decision
      ...
```

---

## 4. Directory Roles

step 노드의 `directories` 항목.

| Role | 의미 | 예 |
|------|------|---|
| `input` | 이 step이 읽어오는 소스 | `01.hand-off-policy/` |
| `output` | 이 step이 생성/배포하는 결과 | `02.draft/` |
| `reference` | 읽기 전용 참고 자료 | `00.framework/` |
| `instruction` | 실행 규칙·정책 문서 | `tier1_patterns.csv` |

모두 Optional. 디렉토리가 없는 step (순수 계산, API 호출 등)은 `directories` 생략.

---

## 5. Decision Branch Conditions

`branches.on:` 허용 값은 `judge` 타입별로 정해짐.

| Judge | 허용 조건 |
|-------|---------|
| `HITL` | `approved` · `rejected` · `escalated` |
| `HITLFE` | `auto-approved` · `escalated` · `rejected` |
| `HOTL` | `passed` · `flagged` |
| `HOOTL` | `completed` · `failed` |

`goto` 생략 시 → sequential next node.  
`on: approved` 등 정상 경로는 생략 가능 (암묵적 next).

---

## 6. Phase Schema

```yaml
[phase_id]:
  id: [phase_id]               # discovery | development | testing
  label: [string]              # 표시 이름
  status: completed | active | pending
  show_wrapper: true | false   # false → Mermaid phase subgraph 생략 (기본 true)
  default_judge: HITL | ...    # Optional — 하위 decision 기본값
  steps: [list of step | decision | group]
  artifacts: [list]            # 완료 산출물 요약
  success_criteria: [list]     # testing phase 필수, 3개 이상
```

---

## 7. Full Example

```yaml
module:
  name: AI Chatbot Policy Framework
  id: 02.AI-Chatbot-Policy
  version: "1.0.0"
  owner: owner@example.com
  created: 2026-05-21

development:
  id: development
  label: 개발 & 구현
  status: active
  show_wrapper: false
  steps:
    - type: step
      id: acp-s-001
      label: "핸드오프 정책 v1.0 개발"
      status: completed
      directories:
        - role: output
          path: 01.hand-off-policy/
      deliverables:
        - golden_dataset_v1.0.0.csv
        - tier1_patterns_v1.0.0.csv

    - type: group
      id: acp-g-001
      label: "정책 업데이트 사이클"
      steps:
        - type: step
          id: acp-s-005
          label: "요구사항 분석"
          directories:
            - role: input
              path: 01.hand-off-policy/
          deliverables:
            - 변경 요구사항 문서

        - type: step
          id: acp-s-006
          label: "hand-off 파일을 draft 폴더로 복제"
          directories:
            - role: input
              path: 01.hand-off-policy/
            - role: output
              path: 02.draft/

        - type: step
          id: acp-s-007
          label: "Discovery & Planning"
          directories:
            - role: output
              path: 02.draft/
          sub_steps:
            - 요구사항 상세 분석
            - 정책 구조 설계
            - 평가 메트릭 정의
            - 테스트 전략 수립

        - type: decision
          id: acp-d-001
          label: "hand-off 확정 검토"
          judge: HITL
          owner: owner@example.com
          sla: "24시간 이내"
          branches:
            - on: rejected
              goto: acp-s-007

        - type: step
          id: acp-s-008
          label: "기존 hand-off 파일을 history로 이동"
          directories:
            - role: input
              path: 01.hand-off-policy/
            - role: output
              path: 99.history-policy/

        - type: step
          id: acp-s-009
          label: "draft 파일을 hand-off 폴더로 이동"
          directories:
            - role: input
              path: 02.draft/
            - role: output
              path: 01.hand-off-policy/

testing:
  id: testing
  label: 테스트 & 평가
  status: active
  steps:
    - type: step
      id: acp-s-010
      label: "핸드오프 정책 검증"
      validation:
        - Golden dataset 정확도
        - Tier별 성능 비교

    - type: decision
      id: acp-d-002
      label: "품질 기준 달성 여부 평가"
      judge: HITLFE
      owner: owner@example.com
      threshold: "F1 < 0.87"
      branches:
        - on: escalated
          goto: acp-s-010

  success_criteria:
    - 핸드오프 정책 검증 완료 (F1 ≥ 0.87)
    - 메시지 픽싱 정확도 92% 이상
    - 통합 테스트 완료
```
