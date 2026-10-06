# 시작하기 (v0.13.1)

> **Python 환경**: 스킬 스크립트는 `requirements.txt`(PyYAML, rdflib, jsonschema, duckdb, pyshacl)만 있으면 돈다. `mso-workflow-optimizer`가 만든 `graph.py`를 LangGraph로
> 실행하려면 `requirements-langgraph.txt`(langgraph)가 추가로 필요하다(없으면 선형 fallback). venv는 저장소에 내장하지 않는다 — `bash install.sh --venv`가 저장소 밖
> `~/.mso/venv`(`MSO_VENV`로 변경)에 만들어 둘 다 설치한다.

## 0. 설치

```bash
# 옵션 A: install.sh (직접 symlink)
bash install.sh               # Claude Code 전용
bash install.sh --codex       # Codex: ~/.agents/skills
bash install.sh --gemini      # Antigravity: ~/.gemini/antigravity/skills
bash install.sh --all         # Claude + Codex + Gemini(Antigravity)
bash install.sh --codex-legacy # 구형 ~/.codex/skills 설치가 명시적으로 필요할 때만

# 옵션 B: sync-agents-global.sh (글로벌 링크 허브 경유)
bash 00_agents_global_links/sync-agents-global.sh sync
```

Codex user-scope skill 정본은 `~/.agents/skills/`이다. 동일한 skill name을 서로 다른
소스에서 `~/.agents/skills/`와 `~/.codex/skills/` 양쪽에 설치하지 않는다. 위치 규칙은
[Codex Skills 공식 문서](https://learn.chatgpt.com/codex/build-skills)를 따른다.

---

## 1. 새 프로젝트 부트스트랩 (mso-repository-setup)

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py \
  --target /path/to/project \
  --name "프로젝트 이름" \
  --id "project-id-01"
```

생성되는 구조:

```
project/
├── agent-context/
│   ├── index/index.yaml
│   ├── workflow/                  # *.abox.ttl = workflow SSOT, *.yaml = migration/edit layer
│   └── work-memory/
│       ├── schema.yaml
│       ├── auditlog/   worklog/
│       ├── track-record/  release-record/
│       └── insight-record/
└── .gitignore
```

### 기존 프로젝트 점검

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py --check /path/to/project
```

### Hook 등록 (auditlog 자동 기록 + 기록 판단 넛지)

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py --hook /path/to/project
```

`.claude/settings.json`에 PostToolUse audit/scaffold, Stop/PreCompact commit,
SessionStart check/release, UserPromptSubmit workflow/UUG context hook이 등록된다.
Stop hook은 worklog를 자동 생성하지 않는다.
Codex 프로젝트에서는 provider를 명시한다.

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py --hook /path/to/project --provider codex
```

이 경우 `.codex/scripts/`에 hook 스크립트가 복사되고 `.codex/config.toml`에
PostToolUse audit/scaffold, Stop/PreCompact commit, SessionStart check/release,
UserPromptSubmit workflow/UUG context hook이 등록된다. `.codex/hooks.json`은 빈
compatibility 파일이다. Codex hook 이벤트와 stdout 동작은
[OpenAI Codex Hooks 공식 문서](https://learn.chatgpt.com/codex/hooks)를 따른다.

Antigravity 프로젝트에서도 provider를 명시한다.

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py --hook /path/to/project --provider antigravity
```

이 경우 `.agents/scripts/`에 hook 스크립트와 camelCase 변환 어댑터
(`adapter_antigravity.py`)가 복사되고, `.agents/hooks.json`의 hook-name(`mso-work-memory`)
아래에 `PostToolUse`(audit/scaffold), `Stop`(stop-check/commit), `PreInvocation`
(work-memory-check/release-context/workflow-context/UUG-context)가 등록된다.
Antigravity에는 Claude/Codex의 `SessionStart`/`UserPromptSubmit`/`PreCompact`에 직접
대응하는 이벤트가 없어, 어댑터가 `PreInvocation`을 `invocationNum==0`에서만 실행되는
"session" 모드(SessionStart 근사)와 매 호출마다 실행되는 "turn" 모드(UserPromptSubmit
근사)로 나눠 처리한다. hooks.json 스펙은
[Antigravity Hooks 공식 문서](https://antigravity.google/docs/hooks/)를 따른다.

> hook 프로세스의 cwd가 workspace root라는 가정, exit code/timeout 처리,
> `.agents/hooks.json`과 전역 `~/.gemini/config/hooks.json`의 우선순위는 공식 문서에도
> 없어 실제 Antigravity 세션에서 아직 검증하지 못했다. 상세는
> `planning/mso-PLAN-antigravity-provider-support.md` §7을 본다.

workflow cursor는 provider-neutral `.mso/state/workflow-cursor.json`을 사용한다.
v0.10.0의 `.claude/state/workflow-cursor.json`은 호환 읽기·삭제만 지원한다.

---

## 2. Scaffold 정의 (mso-scaffold-design)

`index.yaml` 이 repository 구조의 SSOT다. 모든 모듈·서브디렉토리·참조를 여기에 등록한다.

```bash
SF=~/.claude/skills/mso-scaffold-design/scripts/sf_node.py

# 스키마 확인
python3 $SF show project
python3 $SF show module
python3 $SF show subdir

# 모듈 스캐폴드 생성 (stdout → index.yaml 의 modules: 에 붙여넣기)
python3 $SF scaffold module --id "01.core"

# index.yaml 검증
python3 $SF validate agent-context/index/index.yaml

# 파일시스템과 선언 대조
python3 $SF inventory agent-context/index/index.yaml

# 계층 트리 출력 (sub_index 포함)
python3 $SF tree agent-context/index/index.yaml
```

`index.yaml` 최소 예시:

```yaml
project:
  name: "My Project"
  id: "my-project-01"
  description: "TODO"
  owner: "owner@example.com"
  updated: "2026-05-26"
  version: "0.1.0"
  root_offset: "../.."

modules:
  - id: 01.core
    path: 01.core/
    description: 핵심 로직
    subdirs:
      - path: 00.context/
        role: context
        description: 배경 문서
      - path: 01.scripts/
        role: scripts
        description: 실행 스크립트
    key_files: [README.md]
    status: active
```

---

## 3. Workflow 정의 (mso-workflow-design)

workflow TTL ABox(`*.abox.ttl`)가 SSOT다. 기존 YAML은 편집/마이그레이션 레이어이며, Markdown·Mermaid는 변환 산출물이므로 직접 편집하지 않는다.

```bash
WF=~/.claude/skills/mso-workflow-design/scripts/wf_node.py
WFTTL=~/.claude/skills/mso-workflow-design/scripts/wf_to_ttl.py
WFMIG=~/.claude/skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py

# 스키마 확인
python3 $WF show step
python3 $WF show decision   # judge 5-level 포함
python3 $WF show eval

# 노드 스캐폴드 생성 (stdout → workflow YAML 에 붙여넣기)
python3 $WF scaffold step --id "s-001"
python3 $WF scaffold decision --id "d-001" --decision-subject user
python3 $WF scaffold eval --id "e-001"

# workflow YAML 검증
python3 $WF validate agent-context/workflow/workflow-00.yaml

# scaffold 정합성 cross-check
python3 $WF validate agent-context/workflow/workflow-00.yaml \
  --scaffold agent-context/index/index.yaml

# harness manifest 생성 (harness 보유 metric eval 노드 → CI)
python3 $WF harness-manifest agent-context/workflow/workflow-00.yaml \
  --out ci-manifest.json

# 레거시 YAML → TTL 정본 마이그레이션 / drift check
python3 $WFMIG agent-context/workflow
python3 $WFMIG agent-context/workflow --check
python3 $WFTTL validate agent-context/workflow/workflow-00.yaml
```

workflow YAML 시작점은 `skills/mso-workflow-design/assets/module-workflow-template-00.yaml` 을 복사해 사용한다.

### Mermaid 변환 (관측성, 선택)

```bash
MD=~/.claude/skills/mso-workflow-design/scripts

# 단일 모듈 → 통합 마크다운
python3 $MD/workflow_to_markdown.py agent-context/workflow/workflow-00.yaml

# 전체 시각화 세트 (validate 선행 포함)
python3 $MD/workflow_to_mermaid.py --all
```

---

## 4. Work-Memory 사용 (mso-work-memory)

```bash
export WORKMEM_DIR=./agent-context/work-memory
WM=~/.claude/skills/mso-work-memory/scripts/wm_node.py

# entry 생성
python3 $WM new issue-note \
  --title "timeout 누락 발견" --tags "policy,timeout" --module "01.core"

python3 $WM new agent-decision \
  --title "retry 로직 추가 결정" --tags "retry,resilience"

python3 $WM new alternatives-record \
  --title "재시도 정책 3안 비교" --tags "retry,decision"

python3 $WM new user-decision \
  --title "v2 마감 연기 승인" --tags "schedule"

# 통계
python3 $WM stats

# 검증
python3 $WM validate ./agent-context/work-memory

# 단일 entry 조회
python3 $WM show IN-0001

# 그래프 traversal
python3 $WM graph IN-0001 --depth 2 --direction both
```

### entry 타입 정리

| 타입 | prefix | 저장 위치 |
|------|--------|-----------|
| issue-note | IN | track-record/issue-note/ |
| agent-decision | AD | track-record/agent-decision/ |
| alternatives-record | AR | track-record/alternatives-record/ |
| user-decision | UD | track-record/user-decision/ |
| trouble-shooting | TS | track-record/trouble-shooting/ |
| episode | EP | insight-record/episodes/ |
| pattern | PT | insight-record/patterns/ |
| principle | PR | insight-record/principles/ |
| auditlog | AU | auditlog/ (hook 자동) |
| worklog | WL | worklog/ (workflow TTL node 실행 기록) |

---

## 5. Hook 동작 확인

hook 등록 후 실제 동작 테스트:

```bash
# auditlog hook 수동 실행
echo '{"tool_name":"Bash","tool_input":{"command":"git status"},"session_id":"test","hook_event_name":"PostToolUse"}' \
  | WORKMEM_DIR=./agent-context/work-memory \
    python3 ~/.claude/skills/mso-work-memory/hooks/auditlog.py

# Stop/PreCompact hook 수동 실행 (worklog 자동 생성 없음)
WORKMEM_DIR=./agent-context/work-memory \
  bash ~/.claude/skills/mso-work-memory/hooks/commit-work-memory.sh

# 생성 확인
ls agent-context/work-memory/auditlog/
```


## 6. v0.7 Workflow 정의·검증·관측 흐름

v0.7부터 workflow 정본은 Rail/Stream edge-first ABox다. 신규 워크플로는 v0.7 어휘로
작성하고, 기존 v0.6 ABox는 마이그레이션한다.

```bash
# v0.6 → v0.7 변환 (sibling .v07.abox.ttl 생성 — 검토 후 원본 교체)
python3 skills/mso-workflow-design/scripts/migrate_abox_v06_to_v07.py agent-context/workflow

# SSOT 검증 (v0.6/v0.7 자동 감지)
python3 skills/mso-workflow-design/scripts/validate_abox.py agent-context/workflow

# property chain 파생 + trust 계산 + 관측
python3 skills/mso-workflow-design/scripts/materialize_v07.py agent-context/workflow
python3 skills/mso-workflow-design/scripts/trust_v07.py agent-context/workflow \
  --report agent-context/observability/trust-report.md
python3 skills/mso-graph-observability/scripts/observe_graph.py --root .
```

hook을 등록하면 `.abox.ttl` 저장 시 위 체인이 자동 실행된다:

```bash
cp skills/mso-workflow-design/hooks/workflow-check.sh .claude/scripts/
# .claude/settings.json 의 PostToolUse 에 등록 (mso-repository-setup init 참조)
```

## 7. 연관 저장소 work-memory (mso-work-memory-link, v0.13.0)

엄브렐러 repo 루트에서 세션을 열면 훅은 루트 work-memory만 커밋한다. 하위 서브모듈이나 별도 경로의 MSO 저장소에도 기록하고
커밋하려면 등록부를 쓴다. `agent-context/work-memory/linked-repos.yaml`(선택):

```yaml
discover_gitmodules: true          # 기본 true. work-memory가 있는 서브모듈을 자동 발견 (autocommit 은 꺼짐)
linked_repos:
  - name: child-repo
    path: child-repo        # 절대, ~, 또는 루트 기준 상대
    autocommit: true               # Stop 훅이 이 저장소의 work-memory 만 자동 커밋
```

```bash
LINK=~/.claude/skills/mso-work-memory-link/scripts/wm_link.py
python3 $LINK status                          # 저장소별 autocommit, git 건강, work-memory 미커밋, 훅 사본 일치
python3 $LINK add mso ~/path/to/repo --autocommit
python3 $LINK autocommit child-repo on   # 발견만 된 서브모듈은 항목을 새로 만든다
python3 $LINK sync-hooks                      # 훅 사본과 스킬 최신판 비교 (기본 dry-run, --apply 로 교체)
python3 $LINK verify                          # 경로, git HEAD, 훅 문법

# 연관 저장소 work-memory 에 기록
WM=~/.claude/skills/mso-work-memory/scripts/wm_node.py
python3 $WM new agent-decision --title "..." --repo-name child-repo
python3 $WM stats --repo ~/path/to/repo       # 경로로 직접 지정해도 된다
```

- 자동 커밋은 해당 저장소의 work-memory 경로만 stage 하고 push 하지 않으며 서브모듈 포인터는 건드리지 않는다. `MSO_WM_LINKED=0`으로 이 확장만 끈다.
- `sync-hooks --apply`는 `.claude/` 훅 사본을 바꾸므로 사용자 승인 후에 실행한다.
- 포함하는 git의 HEAD 객체가 손상된 저장소는 `verify`가 `BAD`로 표시한다. 그런 저장소는 `autocommit`을 끄고 먼저 복구한다.

## 8. Artifact 층 (TTL registry, v0.13.0)

artifact의 이름 규약, 형식, 디렉토리, 소비자 유형을 TTL로 정의하고 검증한다. 모델은 [artifact-model.md](artifact-model.md)를 본다.
registry는 `agent-context/index/artifacts.abox.ttl`이다.

```turtle
art:reportDraft a wf:Artifact, wf:RegisteredArtifact ;
    rdfs:comment "날짜별 리포트 초안"@ko ;
    wf:hasArtifactType wf:Document ; wf:consumerType wf:Hybrid ; wf:inModule "reports" ;
    wf:hasConvention art:reportDraft_c1 .
art:reportDraft_c1 a wf:ArtifactConvention ;
    wf:directoryTemplate "reports/[date]/" ; wf:namingConvention "[date]-report-[topic]" ; wf:fileFormat "md" ;
    wf:hasParam [ wf:paramName "date" ; wf:paramType wf:DateYmd ], [ wf:paramName "topic" ; wf:paramType wf:Slug ] .
```

```bash
# registry + workflow Stream 검증 (SHACL/SPARQL, 교차 층, git HEAD 기준 규약 불변)
python3 skills/mso-workflow-design/scripts/validate_artifact_layer.py --root .

# 실제 파일이 규약에 맞는지 스캔 (항목 날짜로 유효 규약을 고른다)
python3 skills/mso-workflow-design/scripts/validate_artifact_layer.py --root . --scan --json scan.json

# workflow 의 경로·locator 참조가 index 와 registry 에 매핑되는지
python3 skills/mso-scaffold-design/scripts/check_artifact_index.py --root . --suggest
```

- 규약이 바뀌면 개념 IRI는 그대로 두고 새 규약 버전(`art:<name>_c2`)을 만들고, 이전 것에 `wf:validUntil`과 `wf:supersededBy`를 붙인다.
  커밋된 규약의 세 요소를 직접 고치면 검증기가 Violation으로 잡는다(`--no-history-check`로 끌 수 있다).
- producer/consumer는 속성으로 쓰지 않는다. workflow의 `wf:Stream`이 `art:` IRI를 가리키게 한다.
- 계보 질의는 `skills/mso-workflow-design/references/queries/artifact-lineage.rq`를 registry와 workflow ABox를 합친 그래프에 실행한다.
- 패턴에서 draft workflow를 만들려면 `pattern_to_workflow_draft.py --pattern PT-0001`을 쓴다(절차형 pattern, 에피소드 2개 이상, 결과는 항상 draft).
- 이 층의 시험은 python 3.11 이상과 `pyshacl`이 필요하다.

