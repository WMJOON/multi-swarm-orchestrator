# index.yaml Schema

## 설계 원칙

- **index.yaml이 SSOT** — 실제 디렉토리 트리는 이 선언을 따른다.
- **id는 불변** — 한번 부여하면 변경 금지 (workflow YAML이 path로 참조).
- **스킬은 구조만 강제** — 네이밍 패턴·prefix 의미·role enum 등은 프로젝트 컨벤션 영역.

---

## Table of Contents

1. [Top-level Structure](#1-top-level-structure)
2. [Project Schema](#2-project-schema)
3. [Module Schema](#3-module-schema)
4. [Subdir Schema](#4-subdir-schema)
5. [Data Registry](#5-data-registry)
6. [References (Cross-module)](#6-references-cross-module)
7. [Structural Invariants](#7-structural-invariants)
8. [Full Example](#8-full-example)

---

## 1. Top-level Structure

```yaml
project:
  # — project.schema.yaml —

modules:
  - # — module.schema.yaml —
  - # — ...

data_registry:
  - # — data_registry.schema.yaml, optional —
```

`project:` 1개, `modules:` 1개 이상. `data_registry:`는 optional이다.

---

## 2. Project Schema

```yaml
project:
  name: [string]            # 필수 — 표시 이름
  id: [string]              # 필수 — 고유 식별자 (네이밍 컨벤션은 프로젝트 정의)
  description: |            # 필수 — 멀티라인 허용
    여러 줄 가능
  owner: [string]           # 필수
  updated: [string]         # 필수 — 갱신일 (형식은 프로젝트 정의)
  version: [string]         # optional — semver 권장
```

---

## 3. Module Schema

```yaml
- id: [string]              # 필수 — 디렉토리명과 동일, unique, 불변
  path: [string]            # 필수 — 끝 '/' 필수
  description: [string]     # 필수
  subdirs: [list]           # optional — subdir.schema.yaml
  key_files: [list]         # optional — 모듈 루트 주요 파일
  references: [list]        # optional — 모듈 간 의존
  status: active | deprecated | planned   # optional, default active
```

> 네이밍 컨벤션(예: `NN.kebab-case`)은 프로젝트에서 정의한다.  
> 예시: [assets/conventions-example.md](../assets/conventions-example.md)

---

## 4. Subdir Schema

```yaml
subdirs:
  - path: [string]          # 필수 — 모듈 path 기준 상대경로, 끝 '/' 필수
    description: [string]   # 필수
    role: [string]          # optional — 자유형 식별자 (프로젝트 enum 권장)
    artifacts: [list]       # optional — 주요 파일 목록
    status: [enum]          # optional
```

`role` 은 자유형 string. 권장 어휘 예시: `code`, `data`, `docs`, `modules`, `archive`, `draft`, `artifacts`, `planning`.  
프로젝트별로 enum 컨벤션을 정의해 일관성을 부여하면 workflow YAML 의 `directories.role` 과 의미 매핑이 가능하다.

---

## 5. Data Registry

`data_registry`는 workflow와 graph observability가 참조하는 Artifact source의 registry다. 기존 `modules[].path`와 `subdirs[].path`는 `data_type=local_file` artifact source로 자동 해석되지만, API/MCP/database처럼 디렉토리가 아닌 source나 더 안정적인 id가 필요한 source는 명시 등록한다.

MSO는 Data Pipeline이 아니라 Artifact Supply Chain을 관측한다. `data_type`은 저장/접근 매체(local_file, api, mcp, database 등)를 뜻하고, `artifact_type`은 소비·운영 의미를 뜻한다. `artifact_type`을 생략하면 graph observability가 보수적으로 추론한다.

지원 `artifact_type` 권장값:

- `knowledge_store`: ontology.ttl, workflow.ttl, SHACL, JSON Schema 등 Agent가 추론/검증하는 구조화 지식 저장소
- `event_store`: work-memory.jsonl, auditlog, worklog 등 실행 기록과 이벤트 저장소
- `local_database`: cache.sqlite, duckdb 등 빠른 조회/질의를 위한 로컬 DB
- `document`: README.md, report.md, prompt.md 등 Human+Agent가 함께 읽고 수정하는 협업 인터페이스
- `media`: html, pdf, pptx, png, svg 등 Human-native 최종 전달물

`resource_kind=file|data`는 v0.4.0 호환 alias이며 신규 작성은 `artifact_type`을 사용한다.

```yaml
data_registry:
  - id: content.draft
    data_type: local_file
    artifact_type: document
    locator: content/draft/
    description: 작성 중인 글 초안

  - id: ontology.workflow
    data_type: local_file
    artifact_type: knowledge_store
    locator: ontology/workflow/
    description: TTL/SHACL 기반 workflow ontology

  - id: google.calendar.primary
    data_type: mcp
    artifact_type: knowledge_store
    locator: mcp://google-calendar/calendars/primary
    description: 기본 Google Calendar MCP resource

  - id: trend.api.search
    data_type: api
    artifact_type: knowledge_store
    locator: https://api.example.com/trends/search
```

Graph observability는 raw locator를 직접 location으로 쓰지 않고 `location: index:<id>`로 표시한다. 실제 경로·엔드포인트는 `locator:` 줄로 분리해 보여준다.

지원 data_type 권장값:

- `local_file`
- `api`
- `mcp`
- `database`
- `object_store`
- `external_url`

## 6. References (Cross-module)

```yaml
references:
  - consumes: [module-id]        # 이 모듈이 입력으로 쓰는 모듈
    artifacts: [list]

  - provides_to: [module-id, ...]  # 산출물을 주는 모듈들
    artifacts: [list]
```

`consumes` / `provides_to` 의 모듈 id 는 `modules[]` 에 존재해야 한다 (스킬 검증).

---

## 7. Structural Invariants (스킬이 검증)

- `project.name`, `id`, `description`, `owner`, `updated` 모두 존재
- 모든 모듈에 `id`, `path`, `description` 존재
- module `id` 는 modules[] 내 unique
- 모든 `path` (모듈·subdir) 는 `/` 로 끝남
- 동일 모듈 내 `subdirs[].path` unique
- `references.consumes` / `provides_to` 가 가리키는 모듈 id 가 존재
- `data_registry[].id` 는 data registry 내 unique여야 한다
- `data_registry[].locator` 는 data_type에 맞는 실제 접근자다
- `data_registry[].artifact_type` 는 선택값이며, 명시 시 지원 enum 중 하나여야 한다
- `data_registry[].resource_kind` 는 deprecated compatibility alias다

> 그 외 네이밍 패턴·prefix·role enum 은 **프로젝트 컨벤션**으로 관리한다.

---

## 8. Full Example

```yaml
project:
  name: AI Chatbot 1.0
  id: 02.Chatbot-1.0
  description: 커머스 CS 자동화를 위한 AI 챗봇 프로젝트
  owner: owner@example.com
  updated: 2026-05-21
  version: "1.0.0"

modules:
  - id: 01.consultdata
    path: 01.consultdata/
    description: 상담 데이터 분석 모듈
    subdirs:
      - path: 00.context/
        role: context
        description: 프로젝트 컨텍스트 문서
      - path: 01.scripts/
        role: scripts
        description: 분석 스크립트
    key_files: [README.md, CLAUDE.md]
    references:
      - provides_to: [02.AI-Chatbot-Policy]
        artifacts: [상담 데이터 분석 결과]

  - id: 02.AI-Chatbot-Policy
    path: 02.AI-Chatbot-Policy/
    description: AI 챗봇 정책 산출물
    references:
      - consumes: 01.consultdata
        artifacts: [상담 데이터 분석 결과]
      - provides_to: [04.AIKON7]
        artifacts: [라우팅 정책]
```
