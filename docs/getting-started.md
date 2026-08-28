# 시작하기 (v0.12.1)

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
