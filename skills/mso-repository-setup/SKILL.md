---
name: mso-repository-setup
description: >
  MSO 스킬 팩의 init 진입점. 새 프로젝트(또는 기존 프로젝트)에 agent-context/
  표준 디렉토리 트리를 부트스트랩하고 mso-scaffold-design + mso-workflow-design +
  mso-work-memory 가 동작할 기반을 준비한다.
  다음 상황에서 사용한다:
  (1) 새 프로젝트의 MSO init,
  (2) 기존 프로젝트를 agent-context/ 구조로 마이그레이션,
  (3) work-memory 디렉토리 트리 추가,
  (4) 표준 .gitignore / settings.json hook 등록 안내.
---

# MSO Repository Setup

MSO 스킬 팩이 동작하기 위한 **표준 디렉토리 구조**를 부트스트랩한다.
실제 scaffold/workflow 정의는 본 스킬이 아닌 `mso-scaffold-design` + `mso-workflow-design` 에서.

## What

```bash
python scripts/init.py --target /path/to/project [--name "Project Name"]
```

생성되는 구조:

```
<target>/
├── agent-context/
│   ├── index/
│   │   └── index.yaml                # root_offset: "../.."
│   ├── workflow/                     # mso-workflow-design 영역
│   └── work-memory/
│       ├── schema.yaml               # mso-work-memory 표준 스키마 사본
│       ├── auditlog/   worklog/
│       ├── track-record/{issue-note, agent-decision, user-decision, trouble-shooting}/
│       └── insight-record/{episodes, patterns, principles}/
└── .gitignore                        # agent-context/work-memory/.zvec/ 등록
```

## Flow (다음 진입점)

```
mso-repository-setup
        │
        ├──> [trigger: "scaffold 설계"]   →  mso-scaffold-design
        │                                       (index.yaml 모듈·subdir 정의)
        │
        ├──> [trigger: "워크플로우 설계"] →  mso-workflow-design
        │                                       (workflow YAML · validation/decision 노드)
        │
        ├──> [harness: logging]          →  hook → work-memory/auditlog
        │                                       work-memory/worklog
        │
        ├──> [decision/trigger]          →  mso-work-memory
        │                                       (track-record → insight-record)
        │
        └──> [trigger: 추후]              →  optimization layer (v2)
```

## Entry Points

| 명령 | 동작 |
|---|---|
| `init.py --target <path>` | 표준 디렉토리 + 최소 index.yaml/schema.yaml 생성 |
| `init.py --check <path>` | 기존 구조가 표준에 부합하는지 진단 |
| `init.py --migrate <path>` | 기존 평탄 구조 → agent-context/ 이전 (단순 mv) |

## Non-Goals

- index.yaml 의 모듈·subdir 정의 → `mso-scaffold-design`
- workflow yaml 작성 → `mso-workflow-design`
- 작업 기록 (entry CRUD, 검색, 그래프) → `mso-work-memory`
- hook 자동 등록 (settings.json 수정) → 안내만, 사용자 승인 후 직접 등록

## Dependencies

- Python 3.10+ (stdlib + pyyaml)
- 이후 사용을 위해: `mso-scaffold-design`, `mso-workflow-design`, `mso-work-memory` 스킬 설치 권장

## Pack 멤버 (name-only)

이 스킬은 다음 스킬들과 협업한다. 실제 동작은 각 스킬이 담당:

- **mso-scaffold-design** — index.yaml SSOT, 계층 sub_index 지원
- **mso-workflow-design** — workflow YAML, 노드 스키마, harness manifest
- **mso-work-memory** — jsonl entry, zvec 검색, relations 그래프
- **mso-orchestration** — 진입점·라우팅 (이 스킬을 init 으로 호출)

## 참고 자료

- [scripts/init.py](scripts/init.py) — 부트스트랩 CLI
- [assets/index-template.yaml](assets/index-template.yaml) — 최소 index.yaml
- [assets/gitignore-template](assets/gitignore-template) — .gitignore 추가 항목
