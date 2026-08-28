---
name: mso-repository-setup
description: >
  MSO 스킬 팩의 init 진입점. 새 프로젝트(또는 기존 프로젝트)에 agent-context/
  표준 디렉토리 트리를 부트스트랩하고 mso-scaffold-design + mso-workflow-design +
  mso-graph-observability + mso-work-memory 가 동작할 기반을 준비한다.
  다음 상황에서 사용한다:
  (1) 새 프로젝트의 MSO init,
  (2) 기존 프로젝트를 agent-context/ 구조로 마이그레이션,
  (3) work-memory 디렉토리 트리 추가,
  (4) work-memory hook(auditlog·worklog·work-memory-check) 과 scaffold-check hook 을
      .claude/ 또는 .codex/ 에 copy-form 으로 자동 등록 (--hook, --provider),
  (5) artifact stream TTL이 있으면 index/sub_index/data_registry 스캔·연결을 점검할
      후속 진입점(mso-scaffold-design, mso-graph-observability)을 안내,
  (6) uug-grounding 연동: UserPromptSubmit 시 UUG가 grounding한 target_project 가
      현재 레포와 다르면 그 프로젝트 agent-context 위치를 넛지(uug-context-hook,
      Claude/Codex 공통, --hook 시 자동 등록),
  (7) v0.8.1 적용 시 폐기된 Hermes Bridge 설정과 전역 skill 링크를 정리한다.
  (8) --provider antigravity: Antigravity 의 camelCase hooks.json(PostToolUse/
      Stop/PreInvocation) 에 work-memory/scaffold-check hook 을 adapter_antigravity.py
      경유로 등록 (SessionStart/UserPromptSubmit 미대응 이벤트는 PreInvocation 으로 근사).
metadata:
  version: "0.12.1"
  triggers:
    - "v0.8.1 적용"
    - "Hermes 설정 정리"
    - "hermes cleanup"
    - "mso-hermes-bridge 정리"
    - "Hermes Bridge 폐기"
---

# MSO Repository Setup

MSO 스킬 팩이 동작하기 위한 **표준 디렉토리 구조**를 부트스트랩한다.
실제 scaffold/workflow 정의는 본 스킬이 아닌 `mso-scaffold-design` + `mso-workflow-design` 에서.
artifact stream TTL 확인 후 index/sub-module 연결 점검은 `mso-scaffold-design`의 validate/inventory와
`mso-graph-observability`의 artifact-stream report를 함께 사용한다.

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
│       ├── track-record/  release-record/
│       └── insight-record/           # 타입별 aggregate JSONL
├── .gitignore                        # .zvec/, .mso/state/, legacy .claude/state/ 등록
├── .claude/                          # --hook --provider claude 시 (copy-form)
│   ├── settings.json                 # Stop·PreCompact·PostToolUse·UserPromptSubmit hook 등록
│   ├── scripts/                      # auditlog.py · commit-work-memory.sh · work-memory-check.sh · stop-check.sh · scaffold-check.sh · sf_node.py · uug-context-hook.py 사본
│   └── references/schemas/           # scaffold index schema 사본
├── .codex/                           # --hook --provider codex 시 (copy-form)
│   ├── config.toml                   # PostToolUse·Stop·PreCompact·SessionStart·UserPromptSubmit
│   ├── hooks.json                    # empty compatibility file
│   ├── scripts/                      # auditlog.py · commit-work-memory.sh · work-memory-check.sh · stop-check.sh · scaffold-check.sh · sf_node.py 사본
│   └── references/schemas/           # scaffold index schema 사본
└── .agents/                          # --hook --provider antigravity 시 (copy-form)
    ├── hooks.json                    # hook-name("mso-work-memory") 키 하위 PostToolUse·Stop·PreInvocation
    ├── scripts/                      # 위 스크립트 전체 + adapter_antigravity.py(camelCase I/O 변환) · sf_node.py 사본
    └── references/schemas/           # scaffold index schema 사본
```

hook 자동 등록 (디렉토리 부트스트랩과 별개 단계):

```bash
python scripts/init.py --hook /path/to/project \
  --worthy-paths "scripts config .github/workflows .claude README.md"

python scripts/init.py --hook /path/to/project --provider codex \
  --worthy-paths "agent-context .mso .codex AGENTS.md README.md"

python scripts/init.py --hook /path/to/project --provider antigravity \
  --worthy-paths "agent-context .mso .agents AGENTS.md README.md"
```

hook 스크립트를 `.claude/scripts/` 로 **복사**하고 settings.json 은 `$CLAUDE_PROJECT_DIR`
상대로만 참조한다(절대·스킬 경로를 커밋 파일에 박지 않음 → CI·타 머신 이식성).
Codex는 `.codex/scripts/` 로 복사하고 `.codex/config.toml`에 공식 hook 이벤트를
등록한다. 프로젝트 루트는 wrapper가 `PROJECT_DIR`로 정규화한다. `.codex/hooks.json`은 중복 실행 방지를 위해 빈 compatibility 파일로
함께 갱신한다. `scaffold-check.sh` 는 `sf_node.py validate/inventory` 를 실행해
index SSOT 와 실제 디렉토리의 불일치를 non-blocking guardrail 로 알린다.
`--worthy-paths` 는 "결정 가치 있는" 경로(`WM_WORTHY_PATHS`)를 주입한다. 미지정
재실행에서는 기존 Claude/Codex 설정값을 보존한다.
`uug-context-hook.py` 는 UUG 가 grounding한 `target_project` 가 현재
레포와 다르고 그 프로젝트에 `agent-context/` 가 있을 때만 1줄 넛지를 주입한다.
uug-grounding 이 이 머신에 없으면 `--hook` 이 이 훅의 복사·등록 자체를 생략한다
(MSO만 설치한 사용자의 settings.json 에는 흔적을 남기지 않음). 게이팅은
`MSO_UUG_CONTEXT_INTENTS`(기본 `work-on-project`), 비활성화는 `MSO_UUG_CONTEXT_DISABLED=1`.

### Antigravity (`--provider antigravity`)

Antigravity 는 hooks.json 이 camelCase I/O 계약이고 이벤트도 5개
(`PreToolUse`/`PostToolUse`/`PreInvocation`/`PostInvocation`/`Stop`)뿐이라
Claude/Codex 의 `SessionStart`/`UserPromptSubmit`/`PreCompact` 에 직접 대응하는
이벤트가 없다 (antigravity.google/docs/hooks/ 확인: 2026-08-28). 기존 hook 스크립트를
고치는 대신 `.agents/scripts/adapter_antigravity.py` 가 매 호출을 가로채 변환한다:

| Antigravity 이벤트 | 어댑터 모드 | 근사 대상 | 등록 훅 |
|---|---|---|---|
| `PostToolUse` | `posttooluse` | (그대로) | auditlog.py, scaffold-check.sh |
| `Stop` | `stop` | (그대로) | stop-check.sh, commit-work-memory.sh |
| `PreInvocation`, `invocationNum==0` | `session` | `SessionStart` | work-memory-check.sh, release-context.sh |
| `PreInvocation`, 매 호출 | `turn` | `UserPromptSubmit` | workflow-context-hook.py, uug-context-hook.py |

hooks.json 최상위는 event 가 아니라 hook-name(`mso-work-memory`)으로 키잉되며,
`PostToolUse` 만 Claude/Codex 처럼 matcher(`run_command|write_to_file|
replace_file_content|multi_replace_file_content`)+hooks 그룹 구조이고 `Stop`/
`PreInvocation` 은 matcher 없이 handler 가 배열에 바로 들어가는 flat 구조다.
`PreCompact` 대응 이벤트는 없어 등록하지 않는다(known gap).

> **미검증 가정** — hook 프로세스의 cwd 가 workspace root 라고 가정해 명령을
> 상대경로(`.agents/scripts/...`)로 생성한다. 실제 Antigravity 환경에서
> `--hook --provider antigravity` 최초 적용 후 `PostToolUse`/`Stop` 이 실제로
> 발화하는지 확인 필요 — 상세 근거와 미검증 항목 목록은 이 프로젝트
> `planning/mso-PLAN-antigravity-provider-support.md` (repository-test 밖,
> 프로젝트 루트 기준) 참조.

## Flow (다음 진입점)

```
mso-repository-setup
        │
        ├──> [trigger: "scaffold 설계"]   →  mso-scaffold-design
        │                                       (index.yaml 모듈·subdir·data_registry 정의)
        │
        ├──> [trigger: "워크플로우 설계"] →  mso-workflow-design
        │                                       (workflow TTL ABox · artifact stream · eval 노드/엣지)
        │
        ├──> [trigger: "그래프 관측"]     →  mso-graph-observability
        │                                       (TTL view · artifact-stream report · 개선 리포트)
        │
        ├──> [harness: logging/check]    →  hook → work-memory/auditlog
        │                                       work-memory/worklog
        │                                       scaffold index/inventory check
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
| `init.py --hook <path> [--provider claude] [--worthy-paths "..."]` | work-memory hook + scaffold-check hook + uug-context-hook 을 `.claude/scripts/` 로 복사하고 settings.json(Stop stop-check/commit·PreCompact·PostToolUse·SessionStart·UserPromptSubmit) 등록 (copy-form) |
| `init.py --hook <path> --provider codex [--worthy-paths "..."]` | hook을 `.codex/scripts/`로 복사하고 config.toml(PostToolUse audit/scaffold, Stop·PreCompact commit, SessionStart check/release, UserPromptSubmit workflow/UUG context) 등록. hooks.json은 빈 compatibility 파일로 갱신 |
| `init.py --hook <path> --provider antigravity [--worthy-paths "..."]` | hook + `adapter_antigravity.py` 를 `.agents/scripts/`로 복사하고 `.agents/hooks.json`(hook-name `mso-work-memory` 하위 PostToolUse audit/scaffold, Stop stop-check/commit, PreInvocation[session] check/release, PreInvocation[turn] workflow/UUG context) 등록 |
| `init.py --cleanup-hermes <path>` | v0.8.1 적용: 폐기된 `mso-hermes-bridge` 전역 skill symlink와 프로젝트 `.hermes/mso-context.md`, `.hermes/bridge.sh` 정리 |

### v0.8.1 Hermes Bridge cleanup

Hermes Bridge는 v0.8.1에서 기본 지원을 폐기했다. 이미 v0.8.0을 적용한 프로젝트는 다음 명령으로 MSO가 만든 Hermes Bridge 흔적을 정리한다.

```bash
python scripts/init.py --cleanup-hermes /path/to/project
```

정리 대상:

- `~/.claude/skills/mso-hermes-bridge`, `~/.codex/skills/mso-hermes-bridge`, `~/.gemini/antigravity/skills/mso-hermes-bridge` symlink 또는 broken symlink
- `<project>/.hermes/mso-context.md`
- `<project>/.hermes/bridge.sh`
- 위 파일 제거 후 비어 있는 `<project>/.hermes/`

보수적 경계:

- `~/.hermes/.env`, Hermes gateway/launchd, API key는 MSO 소유가 아니므로 자동 삭제하지 않는다.
- symlink가 아닌 실제 `mso-hermes-bridge` 디렉토리는 기본 유지한다. 정말 삭제하려면 `--force`를 붙인다.
- `agent-context/artifacts/*hermes*` 산출물은 기록물이므로 자동 삭제하지 않고 경로만 알려준다.

## Non-Goals

- index.yaml 의 모듈·subdir 정의 → `mso-scaffold-design`
- workflow yaml 작성 → `mso-workflow-design`
- 작업 기록 (entry CRUD, 검색, 그래프) → `mso-work-memory`
- hook **스크립트 구현**(auditlog/commit-work-memory/work-memory-check/stop-check/uug-context-hook 의 로직,
  antigravity camelCase 변환 어댑터 `adapter_antigravity.py` 포함) → `mso-work-memory`.
- scaffold index/inventory guardrail 구현(scaffold-check.sh, sf_node.py, schema) → `mso-scaffold-design`.
  본 스킬은 해당 스크립트와 의존 파일을 프로젝트 `.claude/`, `.codex/` 또는 `.agents/` 로 복사·등록만 한다(`--hook`).
  단 provider 설정 디렉토리 변경은 HITL 대상이므로 사용자 승인 후 실행.

## Dependencies

- Python 3.10+ (stdlib + pyyaml)
- 이후 사용을 위해: `mso-scaffold-design`, `mso-workflow-design`, `mso-work-memory` 스킬 설치 권장

## Pack 멤버 (name-only)

이 스킬은 다음 스킬들과 협업한다. 실제 동작은 각 스킬이 담당:

- **mso-scaffold-design** — index.yaml SSOT, 계층 sub_index 지원
- **mso-workflow-design** — workflow TTL ABox SSOT, artifact stream/eval node-edge shape, legacy YAML migration layer
- **mso-graph-observability** — TTL 가시화, artifact stream report, runtime improvement view
- **mso-work-memory** — jsonl entry, zvec 검색, relations 그래프
- **mso-orchestration** — 진입점·라우팅 (이 스킬을 init 으로 호출)

## 참고 자료

- [scripts/init.py](scripts/init.py) — 부트스트랩 CLI (`--target/--check/--migrate/--hook`)
- [assets/index-template.yaml](assets/index-template.yaml) — 최소 index.yaml
- [assets/settings-hook-snippet.json](assets/settings-hook-snippet.json) — 수동 등록 참고용 hook 스니펫 (copy-form)
