---
name: mso-repository-setup
version: "0.3.4"
description: >
  MSO 스킬 팩의 init 진입점. 새 프로젝트(또는 기존 프로젝트)에 agent-context/
  표준 디렉토리 트리를 부트스트랩하고 mso-scaffold-design + mso-workflow-design +
  mso-work-memory 가 동작할 기반을 준비한다.
  다음 상황에서 사용한다:
  (1) 새 프로젝트의 MSO init,
  (2) 기존 프로젝트를 agent-context/ 구조로 마이그레이션,
  (3) work-memory 디렉토리 트리 추가,
  (4) work-memory hook(auditlog·worklog·work-memory-check) 을 .claude/ 에
      copy-form 으로 자동 등록 (--hook).
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
├── .gitignore                        # agent-context/work-memory/.zvec/ 등록
└── .claude/                          # --hook 시 (copy-form)
    ├── settings.json                 # Stop·PreCompact·PostToolUse hook 등록
    └── scripts/                      # auditlog.py · worklog.py · work-memory-check.sh 사본
```

hook 자동 등록 (디렉토리 부트스트랩과 별개 단계):

```bash
python scripts/init.py --hook /path/to/project \
  --worthy-paths "scripts config .github/workflows .claude README.md"
```

hook 스크립트를 `.claude/scripts/` 로 **복사**하고 settings.json 은 `$CLAUDE_PROJECT_DIR`
상대로만 참조한다(절대·스킬 경로를 커밋 파일에 박지 않음 → CI·타 머신 이식성).
`--worthy-paths` 는 "결정 가치 있는" 경로(`WM_WORTHY_PATHS`)를 주입한다(미지정 시 기본값).

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
| `init.py --hook <path> [--worthy-paths "..."]` | work-memory hook 을 `.claude/scripts/` 로 복사하고 settings.json(Stop·PreCompact·PostToolUse) 등록 (copy-form) |

## Non-Goals

- index.yaml 의 모듈·subdir 정의 → `mso-scaffold-design`
- workflow yaml 작성 → `mso-workflow-design`
- 작업 기록 (entry CRUD, 검색, 그래프) → `mso-work-memory`
- hook **스크립트 구현**(auditlog/worklog/work-memory-check 의 로직) → `mso-work-memory`.
  본 스킬은 그 스크립트를 프로젝트 `.claude/` 로 복사·등록만 한다(`--hook`).
  단 `.claude/` 변경은 HITL 대상이므로 사용자 승인 후 실행.

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

- [scripts/init.py](scripts/init.py) — 부트스트랩 CLI (`--target/--check/--migrate/--hook`)
- [assets/index-template.yaml](assets/index-template.yaml) — 최소 index.yaml
- [assets/settings-hook-snippet.json](assets/settings-hook-snippet.json) — 수동 등록 참고용 hook 스니펫 (copy-form)
