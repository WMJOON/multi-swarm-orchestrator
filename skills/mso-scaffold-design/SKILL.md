---
name: mso-scaffold-design
version: "0.4.0"
description: >
  Repository Scaffolding(directory/reference/data source/convention)을 규정한다.
  프로젝트 루트의 `index.yaml` 을 정본(SSOT)으로 두고, 모듈·서브디렉토리·
  키 파일·모듈 간 참조를 선언적으로 관리한다. mso-workflow-design가
  workflow를 규정할 때 `directories.path` 로 참조하는 ground truth이며,
  graph observability가 Data node location을 `index:<id>`로 표시할 수 있도록
  local_file/API/MCP/database data source registry를 제공한다.
  노드 단위 스키마(references/schemas/)와 sf_node.py 툴로 validate·scaffold를 지원한다.
  다음 상황에서 사용한다:
  (1) 새 프로젝트의 디렉토리 구조 초기 설계,
  (2) 모듈 추가·rename·삭제,
  (3) 서브디렉토리/key_files 변경,
  (4) 모듈 간 references(consumes/provides_to) 갱신,
  (5) workflow YAML 의 `directories.path` 가 참조하는 경로 등록.
---

# MSO Scaffold Design v2

**Primary**: Repository 디렉토리/참조/컨벤션을 `index.yaml` 한 파일에 선언적으로 규정한다.  
**Secondary**: 규정된 구조를 실제 디렉토리 트리와 대조해 누락·잉여 탐지 (관측성, 후순위).

## Abstraction Principle

이 스킬은 **구조적 검증**만 강제한다. 네이밍 컨벤션은 **프로젝트 영역**.

| 스킬이 강제하는 것 | 프로젝트가 정의하는 것 |
|----------------|------------------|
| 필수 필드 (id, path, description, owner, ...) | id 의 네이밍 패턴 (NN.kebab, snake_case, …) |
| `path` 끝 `/` | subdir prefix 규칙 (`00.`, `01.`, ...) |
| id unique (계층 전역), references → 존재 모듈 id | `role` enum 의 허용값 |
| status enum (active/deprecated/planned) | path 깊이 (1-depth, 2-depth, …) |
| `sub_index` 명시 / max_depth=3 / 순환 차단 | 모듈을 sub 로 분리할지 여부 |
| sub_index + local subdirs/key_files 충돌 ERROR | sub 파일 명명 규칙 (`<module>/index.yaml` 등) |

> 프로젝트별 컨벤션은 [assets/conventions-example.md](assets/conventions-example.md) 를 복사·수정해 `docs/` 또는 `CLAUDE.md` 에 둔다.

## Cross-Reference: mso-scaffold-design ↔ mso-workflow-design

두 스킬은 **양방향 의존** 관계다.

| 스킬 | 책임 | 산출물 |
|------|------|--------|
| **mso-scaffold-design** | Repository 구조(directory/reference/data source/convention) 규정 | `index.yaml` (정본) |
| **mso-workflow-design** | scaffold 위 동작 시퀀스 규정 | `workflow/*-workflow-00.yaml` |

### 의존 규칙

1. **scaffold가 먼저** — workflow YAML 의 `directories.path` 는 `index.yaml` 에 등록된 경로만 참조한다.
2. **scaffold 수정 시** — 디렉토리 rename·삭제·이동이 발생하면 workflow YAML 의 영향 받은 `directories.path` 를 일괄 검토한다.
3. **workflow 수정 시** — 새 경로가 필요하면 **scaffold(index.yaml)에 먼저 등록**한 다음 workflow YAML 에서 참조한다.

> 한쪽 수정이 일어나면 다른 쪽 검토가 필수다.

## SSOT 원칙

> **`index.yaml` 이 SSOT다. 실제 디렉토리 트리는 index.yaml을 따른다.**
> 단일 root yaml 또는 **계층 참조** (root → sub_index → ...) 모두 허용.
>
> - **신규 디렉토리**: 해당 모듈의 index.yaml (root 또는 sub) 에 먼저 등록한 뒤 `mkdir`.
> - **삭제·이동**: yaml 수정과 파일시스템 변경을 한 커밋에 묶는다.
> - **검증**: `sf_node.py validate <root_index.yaml>` (sub_index 자동 해석).
> - **트리 확인**: `sf_node.py tree <root_index.yaml>` 로 계층 평탄화 결과 확인.

### 계층 참조 (Monorepo/Subrepo 패턴)

대형 모듈은 자체 `sub_index` 로 내부 구조를 자율 선언할 수 있다.

```yaml
# root index.yaml
modules:
  - id: 02.AI-Chatbot-Policy
    path: 02.AI-Chatbot-Policy/
    sub_index: 02.AI-Chatbot-Policy/index.yaml   # 명시 (자동 발견 X)
```

```yaml
# 02.AI-Chatbot-Policy/index.yaml (sub)
project:
  id: 02.Chatbot-1.0       # root project.id 와 일치 필수
modules:
  - id: 02.AI-Chatbot-Policy
    path: ./
    subdirs:
      - path: 01.staging/
        description: ...
```

**규칙**:
- `sub_index` 가 있으면 동일 모듈의 `subdirs`/`key_files`/`references` 는 비어야 함 (중복 선언 ERROR).
- sub 파일의 `project.id` 는 root 와 동일해야 함.
- 계층 depth 상한 **3** (root + 2단계). 초과 시 ERROR.
- 순환 참조 차단 (visited-set).
- module id 는 **계층 전역에서 unique**.

## Core Workflow

### Step 1. Scaffold

프로젝트 루트에 `index.yaml` 생성:

```bash
cp .claude/skills/mso-scaffold-design/assets/index-template.yaml index.yaml
```

### Step 2. Define (MOTIF 패턴 적용)

`index.yaml` 은 3개 핵심 MOTIF를 따른다:

| Motif | Required Fields |
|-------|----------------|
| Project Metadata | `project.name`, `id`, `description`, `owner`, `updated` |
| Module Definition | `modules[].id`, `path` (끝 `/`), `description` |
| Subdir Definition | `subdirs[].path` (끝 `/`), `description` |

상세 정의:
- [references/yaml-schema.md](references/yaml-schema.md) — **index.yaml 공식 문법 스펙**
- [assets/conventions-example.md](assets/conventions-example.md) — 프로젝트 컨벤션 작성 템플릿 (예시)

### Step 3. Validate (필수)

```bash
cd .claude/skills/mso-scaffold-design/scripts
python sf_node.py validate ../../../../index.yaml
```

### Step 4. Inventory check (Optional, 후순위)

선언된 구조와 실제 파일시스템을 대조:

```bash
python sf_node.py inventory ../../../../index.yaml
```

> Inventory check는 관측성 산출물이다. 선언이 SSOT.

## Node Schema & Tool (sf_node.py)

### 스키마 파일 (`references/schemas/`)

| 파일 | 대상 노드 | 핵심 정의 |
|------|---------|---------|
| `project.schema.yaml` | top-level `project:` | name, id, description, owner, updated |
| `module.schema.yaml` | `modules[]` | id, path, subdirs/key_files/references |
| `subdir.schema.yaml` | `subdirs[]` | path, role, artifacts |
| `data_registry.schema.yaml` | `data_registry[]` | id, data_type, locator |

### sf_node.py 사용법

```bash
# 스키마 조회
python sf_node.py show module

# 노드 스캐폴드 생성
python sf_node.py scaffold module --id 05.new-module
python sf_node.py scaffold subdir --path 02.data/

# index.yaml 검증 (sub_index 자동 해석, 계층 전역 검증)
python sf_node.py validate index.yaml

# 실제 파일시스템과 대조 (계층 재귀)
python sf_node.py inventory index.yaml

# 계층 구조 트리 출력 (디버깅)
python sf_node.py tree index.yaml
```

## YAML 작성 시 주의사항

### Module ID = 디렉토리명
```yaml
- id: 04.AIKON7          # 디렉토리명과 동일
  path: 04.AIKON7/       # 디렉토리명 + 슬래시
```

### Subdir path는 모듈 path 기준 상대경로
```yaml
modules:
  - id: 01.consultdata
    path: 01.consultdata/
    subdirs:
      - path: 02.data/    # 01.consultdata/02.data/ 를 의미
```

### References는 모듈 ID로 참조
```yaml
modules:
  - id: 02.AI-Chatbot-Policy
    references:
      - consumes: 01.consultdata        # 다른 모듈 id
        artifacts: [상담 데이터 분석 결과]
      - provides_to: [04.AIKON7]
        artifacts: [라우팅 정책]
```

## 검증 체크리스트

**Workflow 정합성 (먼저 확인)**
- [ ] 디렉토리를 삭제·rename한 경우 workflow YAML 의 `directories.path` 를 검색했는가
- [ ] 새 디렉토리를 workflow 가 참조할 예정이면 index.yaml 에 먼저 등록했는가

**Scaffold 구조 (스킬이 검증)**
- [ ] `project.name`, `id`, `owner`, `updated` 모두 존재
- [ ] 모든 모듈에 `id`, `path`, `description` 존재
- [ ] 모듈 id 가 unique (계층 전역)
- [ ] 모든 path (모듈·subdir) 가 `/` 로 끝남
- [ ] 모듈 간 references 가 존재하는 모듈 id 만 참조 (계층 전역 풀)
- [ ] `sub_index` 가 있는 모듈은 동일 위치에 `subdirs`/`key_files`/`references` 가 비어 있음
- [ ] sub 파일의 `project.id` 가 root 와 일치
- [ ] 계층 depth ≤ 3, 순환 참조 없음

**프로젝트 컨벤션 (프로젝트가 정의·검증)**
- [ ] 프로젝트의 id 네이밍 규칙 준수
- [ ] role / status 등의 enum 사용 일관성

## 의존성

```
pyyaml>=6.0
```

## 참고 자료

- **YAML 문법 스펙**: [references/yaml-schema.md](references/yaml-schema.md)
- **네이밍 컨벤션 예시**: [assets/conventions-example.md](assets/conventions-example.md)
- **검증 스크립트**: [scripts/sf_node.py](scripts/sf_node.py)
- **템플릿**: [assets/index-template.yaml](assets/index-template.yaml)
