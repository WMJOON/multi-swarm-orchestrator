# Workflow Patterns

MOTIF와의 구분:

| | MOTIF | Workflow Pattern |
|--|-------|----------------|
| **단위** | step/phase 수준의 구조 | 여러 step·decision을 묶는 사이클 |
| **적용** | 모든 워크플로우에 동일하게 | 해당 상황에만 선택적으로 |
| **내용** | 필드명·구조가 고정 | 사이클 형태는 고정, edit 단계 내용은 모듈마다 다름 |

새 패턴은 3개 이상 모듈에서 동일한 **사이클 형태**가 반복될 때 추가한다.

## Table of Contents

1. [Local File Versioning Pattern](#1-local-file-versioning-pattern)
2. [Git Versioning Pattern](#2-git-versioning-pattern)
3. [Work-Memory Feedback Update Pattern](#3-work-memory-feedback-update-pattern)

---

## 1. Local File Versioning Pattern

Git 없이 파일 시스템 폴더로 버전을 관리할 때.  
**edit 단계의 내용은 모듈마다 다르다** — 이게 MOTIF가 아닌 Pattern인 이유.

### 사이클

```
copy to draft/ → [edit — 모듈별 고유 작업] → {user review} → archive → promote
```

### Gate 매핑

| Stage | Decision Subject | 이유 |
|-------|-------|------|
| copy to draft | step | 원본 보호용 단순 복사 |
| **edit** | step | 내용은 모듈마다 다름 |
| **review** | `user` + `rejected` branch | 회복 불가 영향, 거절 시 edit으로 복귀 |
| archive | step | 이전 버전 이동 |
| promote | step | draft를 production으로 이동 |

> copy/archive/promote는 자동 실행 step. review만 `type: decision` 으로 분리한다.

### YAML 골격

```yaml
- type: group
  id: [mod]-g-001
  label: "[모듈명] 업데이트 사이클"
  steps:
    - type: step
      id: [mod]-s-N
      label: "[파일] draft 폴더로 복제"
      directories:
        - role: input
          path: [production_folder]/
        - role: output
          path: draft/

    - type: step
      id: [mod]-s-N+1
      label: "[모듈별 고유 edit 작업]"   # ← 내용은 여기만 다름
      directories:
        - role: output
          path: draft/

    - type: decision
      id: [mod]-d-N
      label: "확정 검토"
      decision_subject: user
      owner: [책임자 이메일]
      sla: "24시간 이내"
      branches:
        - on: rejected
          goto: [mod]-s-N+1        # 거절 시 edit으로 복귀

    - type: step
      id: [mod]-s-N+2
      label: "기존 파일 history로 이동"
      directories:
        - role: input
          path: [production_folder]/
        - role: output
          path: [history_folder]/

    - type: step
      id: [mod]-s-N+3
      label: "draft 파일 production으로 이동"
      directories:
        - role: input
          path: draft/
        - role: output
          path: [production_folder]/
```

### 폴더 컨벤션

| 역할 | 권장 이름 |
|------|---------|
| 작업 공간 | `draft/` |
| 현재 배포본 | `01.[name]/`, `product/` |
| 이전 버전 | `99.history-*/`, `archive/` |

### Mermaid 렌더링

`type: group` 블록 → Mermaid **nested subgraph** 자동 생성.  
user decision의 `rejected` branch → subgraph 외부로 **점선 엣지** 연결.

### 현재 적용

| 모듈 | edit 단계 내용 | group id |
|------|-------------|----------|
| `02.policy-engine` | hand-off 정책 문서 수정 | `acp-g-001` |
| `03.data-masking` | 마스킹 엔진 코드 수정 | (적용 예정) |

---

## 2. Git Versioning Pattern

Git 저장소 기반. branch → PR → merge 흐름.  
**commit 단계 내용(변경 목적)은 저장소마다 다르다.**

### 사이클

```
feature branch → [commit — 저장소별 고유 변경] → {user: PR review} → merge → tag
```

### Gate 매핑

| Stage | Decision Subject | 이유 |
|-------|-------|------|
| feature branch 생성 | (step) | 단순 브랜치 생성 |
| **commit & push** | step | CI 자동 실행 |
| **PR/MR review** | `user` | Approver 지정, 거절 시 commit으로 복귀 |
| merge to main | (step) | squash or merge |
| tag & release | `user` decision | breaking change 시 확인 |

### YAML 골격

```yaml
- type: group
  id: [mod]-g-001
  label: "[저장소명] 릴리즈 사이클"
  steps:
    - type: step
      id: [mod]-s-N
      label: "feature branch 생성"

    - type: step
      id: [mod]-s-N+1
      label: "[저장소별 고유 변경 커밋]"   # ← 내용은 여기만 다름
      directories:
        - role: output
          path: "git://feature/[name]"

    - type: decision
      id: [mod]-d-N
      label: "PR/MR 리뷰"
      decision_subject: user
      owner: [reviewer 이메일]
      branches:
        - on: rejected
          goto: [mod]-s-N+1

    - type: step
      id: [mod]-s-N+2
      label: "main 브랜치 merge"
      directories:
        - role: output
          path: "git://main"

    - type: decision
      id: [mod]-d-N+1
      label: "릴리즈 태그 확인"
      decision_subject: user
      decision_criteria: "breaking change 포함 여부 확인"
      threshold: "breaking change 포함 시 수동 승인"
      branches:
        - on: escalated
          goto: [mod]-s-N+2
```

### 현재 적용

| 모듈 | commit 내용 | group id |
|------|-----------|----------|
| `04.vendor-x/05.modules/rag-eval` | RAGAS 평가 엔진 수정 | (적용 예정) |

---

## 3. Work-Memory Feedback Update Pattern

work-memory에 누적된 이슈, 결정, 해결, 회고가 workflow TTL 또는 artifact stream graph의 구조적 업데이트 신호가 될 때 사용한다.

**work-memory는 evidence이고, workflow TTL ABox가 SSOT-of-record다.** 관측 Markdown/Mermaid는 TTL에서 재생성되는 파생 뷰이므로 직접 수정하지 않는다.

### 사이클

```
work-memory signal → classify update → edit TTL ABox → validate/regenerate graph → record follow-up memory
```

### Signal 매핑

| Work-memory signal | Workflow / artifact stream 업데이트 후보 |
|--------------------|------------------------------------------|
| 반복 `IN` / `TS` | 실패가 반복되는 step에 validation/eval gate 추가 |
| `AD` / `UD` 정책 변경 | decision node의 `decision_subject`, branch case, criteria 갱신 |
| `EP` / `PT` 패턴 | 여러 workflow에 반복 적용할 Workflow Pattern 후보 |
| `artifact-stream-report` 누락 소비자 | produced artifact의 downstream consumer, eval, cross-workflow boundary 보강 |
| `PR` 원칙 | scaffold convention 또는 workflow invariant로 승격 검토 |

### Gate 매핑

| Stage | 책임 | 산출물 |
|-------|------|--------|
| signal 수집 | `mso-work-memory` | `IN/AD/UD/TS/EP/PT/PR` entry와 relations |
| update 분류 | agent decision 또는 user decision | TTL 변경 필요 여부, 영향 workflow 범위 |
| TTL 수정 | `mso-workflow-design` | `agent-context/workflow/*.abox.ttl` |
| graph 재생성 | `mso-graph-observability` | workflow graph, artifact-stream graph, runtime analysis |
| follow-up 기록 | `mso-work-memory` | 변경 근거 AD/UD 또는 해결 TS, 필요 시 EP/PT |

### 운영 규칙

1. work-memory entry가 곧바로 graph를 수정하지 않는다. entry는 TTL 편집의 근거와 추적 링크다.
2. workflow node/edge 변경은 반드시 TTL ABox에서 수행한다.
3. artifact-stream graph에서 발견한 누락은 Markdown을 고치지 않고, TTL의 `wf:directory`, `wf:deliverables`, `wf:targetArtifact`, `wf:orderTarget`, `wf:usesTool` 중 필요한 edge를 보강한다.
4. 구조 변경이 사용자 정책·책임 경계를 바꾸면 `UD`로 남기고, agent 권한 내 보수적 정리면 `AD`로 남긴다.
5. 같은 유형의 update가 3개 이상 workflow에서 반복되면 이 파일의 Workflow Pattern 후보로 승격한다.

### TTL 변경 예시

```ttl
<wf:node/release-rel-e-020> a wf:Eval, wf:Node ;
    wf:label "릴리즈 산출물 회귀 평가" ;
    wf:oracleType "metric" ;
    wf:targetArtifact "agent-context/workflow/release-report.jsonl" ;
    wf:criteria "최근 TS에서 반복된 회귀 조건을 통과해야 함" ;
    wf:orderTarget "rel-s-030" ;
    wf:orderArtifact "agent-context/observability/graph/release/eval-report.md" .
```

### 현재 적용 후보

| 후보 | 이유 |
|------|------|
| workflow eval gate 보강 | 반복 TS가 특정 산출물 품질 문제로 모일 때 |
| artifact consumer 보강 | artifact-stream-report가 produced-but-unconsumed artifact를 반복 지적할 때 |
| decision branch 정리 | UD/AD가 같은 decision boundary의 drift를 계속 만들 때 |

---

## Related

- [motif-patterns.md](motif-patterns.md) — MOTIF(구조 단위) 정의
- [gate-levels.md](gate-levels.md) — user/agent decision subject와 파생 intervention level
- [yaml-schema.md](yaml-schema.md) — type:step/decision/group 전체 문법
