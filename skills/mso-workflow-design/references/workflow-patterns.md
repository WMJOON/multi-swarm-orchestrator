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

---

## 1. Local File Versioning Pattern

Git 없이 파일 시스템 폴더로 버전을 관리할 때.  
**edit 단계의 내용은 모듈마다 다르다** — 이게 MOTIF가 아닌 Pattern인 이유.

### 사이클

```
copy to draft/ → [edit — 모듈별 고유 작업] → {HITL review} → archive → promote
```

### Gate 매핑

| Stage | Judge | 이유 |
|-------|-------|------|
| copy to draft | (step, HOOTL 성격) | 원본 보호용 단순 복사 |
| **edit** | (step, HOTL 성격) | 내용은 모듈마다 다름 |
| **review** | **HITL** + `rejected` branch | 회복 불가 영향, 거절 시 edit으로 복귀 |
| archive | (step, HOOTL 성격) | 이전 버전 이동 |
| promote | (step, HOOTL 성격) | draft를 production으로 이동 |

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
      judge: HITL
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
HITL decision의 `rejected` branch → subgraph 외부로 **점선 엣지** 연결.

### 현재 적용

| 모듈 | edit 단계 내용 | group id |
|------|-------------|----------|
| `02.AI-Chatbot-Policy` | hand-off 정책 문서 수정 | `acp-g-001` |
| `03.sensitive-data-masking` | 마스킹 엔진 코드 수정 | (적용 예정) |

---

## 2. Git Versioning Pattern

Git 저장소 기반. branch → PR → merge 흐름.  
**commit 단계 내용(변경 목적)은 저장소마다 다르다.**

### 사이클

```
feature branch → [commit — 저장소별 고유 변경] → {HITL: PR review} → merge → tag
```

### Gate 매핑

| Stage | Judge | 이유 |
|-------|-------|------|
| feature branch 생성 | (step) | 단순 브랜치 생성 |
| **commit & push** | (step, HOTL 성격) | CI 자동 실행 |
| **PR/MR review** | **HITL** | Approver 지정, 거절 시 commit으로 복귀 |
| merge to main | (step) | squash or merge |
| tag & release | HITLFE decision | breaking change 시 에스컬레이션 |

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
      judge: HITL
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
      judge: HITLFE
      threshold: "breaking change 포함 시 수동 승인"
      branches:
        - on: escalated
          goto: [mod]-s-N+2
```

### 현재 적용

| 모듈 | commit 내용 | group id |
|------|-----------|----------|
| `04.AIKON7/05.modules/rag-eval` | RAGAS 평가 엔진 수정 | (적용 예정) |

---

## Related

- [motif-patterns.md](motif-patterns.md) — MOTIF(구조 단위) 정의
- [gate-levels.md](gate-levels.md) — HITL/HITLFE/HOTL/HOOTL 상세
- [yaml-schema.md](yaml-schema.md) — type:step/decision/group 전체 문법
