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
5. [References (Cross-module)](#5-references-cross-module)
6. [Structural Invariants](#6-structural-invariants)
7. [Full Example](#7-full-example)

---

## 1. Top-level Structure

```yaml
project:
  # — project.schema.yaml —

modules:
  - # — module.schema.yaml —
  - # — ...
```

`project:` 1개, `modules:` 1개 이상.

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

## 5. References (Cross-module)

```yaml
references:
  - consumes: [module-id]        # 이 모듈이 입력으로 쓰는 모듈
    artifacts: [list]

  - provides_to: [module-id, ...]  # 산출물을 주는 모듈들
    artifacts: [list]
```

`consumes` / `provides_to` 의 모듈 id 는 `modules[]` 에 존재해야 한다 (스킬 검증).

---

## 6. Structural Invariants (스킬이 검증)

- `project.name`, `id`, `description`, `owner`, `updated` 모두 존재
- 모든 모듈에 `id`, `path`, `description` 존재
- module `id` 는 modules[] 내 unique
- 모든 `path` (모듈·subdir) 는 `/` 로 끝남
- 동일 모듈 내 `subdirs[].path` unique
- `references.consumes` / `provides_to` 가 가리키는 모듈 id 가 존재

> 그 외 네이밍 패턴·prefix·role enum 은 **프로젝트 컨벤션**으로 관리한다.

---

## 7. Full Example

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
